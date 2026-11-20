import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone
from review_auth import AuthUnavailable, Identity, Role, VerifiedToken

from catalog.models import Industry
from .factories import brand, review, reviewer


def identity(role=Role.EDITOR):
    return VerifiedToken(user=Identity(id=uuid4(), username="editor", role=role), expires_at=timezone.now() + timedelta(hours=1))


class ListingTests(TestCase):
    def setUp(self):
        self.author = reviewer()
        self.insurance = Industry.objects.create(name="Insurance", slug="insurance")
        self.finance = Industry.objects.create(name="Finance", slug="finance")
        Industry.objects.create(name="Unused", slug="unused")
        self.alpha = brand("alpha", short_description="Alpha description")
        self.alpha.industries.set([self.insurance, self.finance])
        self.reviews = [review(self.alpha, self.author, slug=f"alpha-{n}", rating=rating) for n, rating in enumerate([5, 5, 1])]
        self.beta = brand("beta")
        self.beta.industries.add(self.finance)
        review(self.beta, self.author, slug="beta-review", rating=5)
        self.unrated = brand("unrated")

    def test_public_results_and_aggregates_are_not_multiplied(self):
        with patch("catalog.api.introspection_lookup") as lookup:
            response = self.client.get("/api/brands/?industry=insurance&industry=finance")
        lookup.assert_not_called()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual([r["slug"] for r in data["results"]], ["beta", "alpha"])
        alpha = data["results"][1]
        self.assertEqual(alpha["average_rating"], 3.67)
        self.assertEqual(alpha["review_count"], 3)
        self.assertEqual(len(alpha["industries"]), 2)
        self.assertEqual(alpha["id"], str(self.alpha.pk))
        self.assertIsNone(alpha["top_review"])
        self.assertEqual(len(data["available_industries"]), 3)

    def test_unrated_last_and_unfiltered_brand_without_industry(self):
        data = self.client.get("/api/brands/?sort=average_rating").json()
        self.assertEqual([r["slug"] for r in data["results"]], ["alpha", "beta", "unrated"])
        last = data["results"][-1]
        self.assertIsNone(last["average_rating"])
        self.assertEqual(last["review_count"], 0)
        self.assertEqual(last["industries"], [])
        self.assertEqual(self.client.get("/api/brands/?sort=review_count").json()["results"][0]["slug"], "unrated")

    def test_sort_ties_are_deterministic(self):
        another = brand("aardvark")
        review(another, self.author, slug="tied-review", rating=5)
        items = self.client.get("/api/brands/").json()["results"]
        self.assertEqual([item["slug"] for item in items[:2]], ["aardvark", "beta"])

    def test_pagination_links_keep_all_criteria(self):
        response = self.client.get("/api/brands/?industry=insurance&industry=finance&sort=-review_count&page_size=1")
        data = response.json()
        query = parse_qs(urlparse(data["next"]).query)
        self.assertEqual(query, {"industry": ["insurance", "finance"], "sort": ["-review_count"], "page_size": ["1"], "page": ["2"]})
        self.assertIsNone(data["previous"])
        self.assertEqual(self.client.get(data["next"]).json()["results"][0]["slug"], "beta")

    def test_empty_and_invalid_queries(self):
        empty = self.client.get("/api/brands/?industry=unused").json()
        self.assertEqual(empty["results"], [])
        self.assertEqual(empty["count"], 0)
        self.assertIsNone(empty["next"])
        for query in ("sort=nonsense", "industry=unknown", "industry=", "page=0", "page=-1", "page=x", "page_size=101", "page_size=0", "page=1&page=2"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/brands/?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("parameter", response.json()["error"])
        response = self.client.get("/api/brands/?industry=unused&page=2")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "page_not_found")

    def test_selected_review_is_explicit_and_plain_text(self):
        chosen = self.reviews[-1]
        chosen.body_html = "<p>Helpful &amp; detailed.</p><p>" + "A long explanation. " * 30 + "</p>"
        chosen.save()
        self.alpha.top_review = chosen
        self.alpha.save()
        selected = self.client.get("/api/brands/?industry=insurance").json()["results"][0]["top_review"]
        self.assertEqual(selected["id"], str(chosen.pk))
        self.assertEqual(selected["rating"], 1)
        self.assertEqual(selected["reviewer_name"], "Sarah K.")
        self.assertTrue(selected["snippet"].startswith("Helpful & detailed. A long"))
        self.assertLessEqual(len(selected["snippet"]), 240)
        self.assertTrue(selected["snippet"].endswith("…"))
        self.assertTrue(selected["published_at"].endswith("Z"))


class UpdateTests(TestCase):
    def setUp(self):
        self.author = reviewer()
        self.brand = brand(short_description="Original")
        self.review = review(self.brand, self.author)
        self.other = brand("other")
        self.foreign_review = review(self.other, self.author, slug="foreign")
        self.lookup = patch("catalog.api.introspection_lookup", return_value=identity()).start()
        self.addCleanup(patch.stopall)

    def update(self, data, **kwargs):
        return self.client.patch("/api/brands/acme/", data=json.dumps(data), content_type="application/json", HTTP_AUTHORIZATION="Bearer opaque-token", **kwargs)

    def test_editor_can_select_update_and_clear(self):
        response = self.update({"short_description": "Changed", "top_review_id": str(self.review.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["short_description"], "Changed")
        self.assertEqual(response.json()["top_review"]["id"], str(self.review.pk))
        self.assertEqual(self.lookup.call_count, 1)
        response = self.update({"short_description": ""})
        self.assertIsNotNone(response.json()["top_review"])
        response = self.update({"top_review_id": None})
        self.assertEqual(response.json()["short_description"], "")
        self.assertIsNone(response.json()["top_review"])

    def test_invalid_selection_cannot_partially_update(self):
        response = self.update({"short_description": "Should not save", "top_review_id": str(self.foreign_review.pk)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["fields"]["top_review_id"][0]["code"], "invalid_selection")
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.short_description, "Original")

    def test_strict_validation_and_plain_text(self):
        for data in ({}, [], None, {"short_description": None}, {"short_description": "x" * 501}, {"name": "New name"}, {"top_review_id": self.review.pk}, {"top_review_id": "0"}, {"top_review_id": "99999999999999999999999"}):
            with self.subTest(data=data):
                self.assertEqual(self.update(data).status_code, 400)
        literal = "<strong>This stays plain text</strong>"
        self.assertEqual(self.update({"short_description": literal}).json()["short_description"], literal)

    def test_authentication_and_live_role_changes(self):
        self.assertEqual(self.client.patch("/api/brands/acme/", data="{}", content_type="application/json").status_code, 401)
        self.assertEqual(self.update({"short_description": "Editor"}).status_code, 200)
        self.lookup.return_value = identity(Role.READER)
        self.assertEqual(self.update({"short_description": "Reader"}).status_code, 403)
        self.lookup.return_value = None
        response = self.update({"short_description": "Inactive"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("invalid_token", response["WWW-Authenticate"])
        self.lookup.side_effect = AuthUnavailable("Unavailable")
        response = self.update({"short_description": "Outage"})
        self.assertEqual(response.status_code, 503)
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.short_description, "Editor")
        self.assertEqual(self.client.get("/api/brands/").status_code, 200)

    def test_invalid_unicode_and_non_json_numbers_leave_data_unchanged(self):
        for text in ("nul\x00character", "unpaired\ud800surrogate"):
            with self.subTest(text=text):
                response = self.update({"short_description": text, "top_review_id": str(self.review.pk)})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "validation_error")
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                response = self.client.patch(
                    "/api/brands/acme/", data='{"short_description":' + constant + '}',
                    content_type="application/json", HTTP_AUTHORIZATION="Bearer token",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "invalid_json")
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.short_description, "Original")
        self.assertIsNone(self.brand.top_review_id)

    def test_json_media_type_not_found_and_methods(self):
        headers = {"HTTP_AUTHORIZATION": "Bearer token"}
        self.assertEqual(self.client.patch("/api/brands/acme/", data="{", content_type="application/json", **headers).json()["error"]["code"], "invalid_json")
        self.assertEqual(self.client.patch("/api/brands/acme/", data="x", content_type="text/plain", **headers).status_code, 415)
        self.assertEqual(self.client.patch("/api/brands/missing/", data='{"short_description":"x"}', content_type="application/json", **headers).status_code, 404)
        self.assertEqual(self.client.post("/api/brands/", data={}).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.patch("/api/brands/acme/", data='{"short_description":"Bearer write"}', content_type="application/json", **headers).status_code, 200)
