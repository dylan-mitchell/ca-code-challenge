import copy
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from catalog.content import plain_text, sanitize_html, short_description, shorten
from catalog.importing import import_content, load_identity_map
from catalog.models import Brand, Industry, Review, Reviewer


def source_data():
    return {
        "industries": [{"term_id": 2, "name": "Insurance", "slug": "insurance"}],
        "users": [{"ID": 2, "display_name": "Sarah K."}],
        "posts": [
            {"ID": 7, "post_type": "brand", "post_title": "Acme", "post_name": "acme-insurance", "post_content": "<p>Brand description.</p>", "post_excerpt": ""},
            {"ID": 12, "post_type": "review", "post_title": "Smooth claim", "post_name": "smooth-claim", "post_content": "<p>Helpful service.</p>", "post_excerpt": "", "post_author": 2, "post_date_gmt": datetime(2026, 5, 19, 20, 29, 13)},
        ],
        "metadata": {7: {"website_url": "https://example.com", "founded_year": "1985"}, 12: {"brand": "7", "rating": "5", "reviewer_name": "Sarah", "reviewer_location": "Denver"}},
        "links": {7: [2]},
    }


class ImportTests(TestCase):
    def setUp(self):
        self.source = source_data()
        self.identities = {2: uuid4()}

    def test_creates_related_records_with_original_dates(self):
        result = import_content(self.source, self.identities)
        self.assertTrue(all(value == {"created": 1, "existing": 0} for value in result.values()))
        brand = Brand.objects.get(wordpress_id=7)
        review = Review.objects.get(wordpress_id=12)
        self.assertEqual(review.brand, brand)
        self.assertEqual(review.reviewer.auth_user_id, self.identities[2])
        self.assertEqual(review.published_at, datetime(2026, 5, 19, 20, 29, 13, tzinfo=timezone.utc))
        self.assertEqual(brand.short_description, "Brand description.")
        self.assertEqual(list(brand.industries.values_list("wordpress_id", flat=True)), [2])
        self.assertIsNone(brand.top_review_id)

    def test_rerun_preserves_local_edits_and_relations(self):
        import_content(self.source, self.identities)
        brand = Brand.objects.get()
        review = Review.objects.get()
        brand.name = "Edited name"
        brand.slug = "edited-slug"
        brand.description_html = "<p>Edited body</p>"
        brand.short_description = "Edited short description"
        brand.top_review = review
        brand.save()
        brand.industries.clear()
        review.rating = 2
        review.body_html = "<p>Edited review</p>"
        review.save()
        profile = Reviewer.objects.get()
        profile.display_name = "Edited profile"
        profile.save()
        before = {model.__name__: list(model.objects.values()) for model in (Brand, Industry, Reviewer, Review)}
        result = import_content(self.source, self.identities)
        after = {model.__name__: list(model.objects.values()) for model in (Brand, Industry, Reviewer, Review)}
        self.assertEqual(before, after)
        self.assertEqual(brand.industries.count(), 0)
        self.assertTrue(all(value == {"created": 0, "existing": 1} for value in result.values()))

    def test_late_failure_rolls_back_entire_main_phase(self):
        self.source["metadata"][12]["rating"] = "6"
        with self.assertRaisesMessage(CommandError, "Review WordPress ID 12"):
            import_content(self.source, self.identities)
        for model in (Industry, Reviewer, Brand, Review):
            self.assertFalse(model.objects.exists())
        self.source["metadata"][12]["rating"] = "5"
        import_content(self.source, self.identities)
        self.assertEqual(Reviewer.objects.get().auth_user_id, self.identities[2])

    def test_missing_or_conflicting_identity_does_not_relink(self):
        with self.assertRaisesMessage(CommandError, "missing auth UUID"):
            import_content(self.source, {})
        self.assertFalse(Industry.objects.exists())
        import_content(self.source, self.identities)
        with self.assertRaisesMessage(CommandError, "conflicts"):
            import_content(self.source, {2: uuid4()})
        self.assertEqual(Reviewer.objects.get().auth_user_id, self.identities[2])

    def test_bad_relationship_date_and_oversized_title_fail(self):
        for field, value in (("post_date_gmt", "0000-00-00 00:00:00"), ("post_title", "x" * 251), ("post_author", 999)):
            broken = copy.deepcopy(self.source)
            broken["posts"][1][field] = value
            with self.subTest(field=field), self.assertRaises(CommandError):
                import_content(broken, self.identities)
            self.assertFalse(Brand.objects.exists())
        self.source["metadata"][12]["brand"] = "999"
        with self.assertRaisesMessage(CommandError, "unknown published brand"):
            import_content(self.source, self.identities)

    def test_slug_conflict_is_not_merged(self):
        existing = Brand.objects.create(name="Native brand", slug="acme-insurance")
        with self.assertRaises(CommandError):
            import_content(self.source, self.identities)
        existing.refresh_from_db()
        self.assertIsNone(existing.wordpress_id)
        self.assertEqual(Brand.objects.count(), 1)
        self.assertEqual(Reviewer.objects.count(), 0)


class ContentTests(SimpleTestCase):
    def test_semantic_html_is_preserved_and_active_content_removed(self):
        html = '<p class="layout" style="color:red" onclick="evil()">Hello <strong>world</strong>.</p><script>evil()</script><a href="javascript:evil()">Unsafe</a>'
        cleaned = sanitize_html(html)
        self.assertIn("<strong>world</strong>", cleaned)
        for forbidden in ("style=", "class=", "onclick", "script", "javascript:", "evil()"):
            self.assertNotIn(forbidden, cleaned)

    def test_plain_text_and_short_description(self):
        self.assertEqual(plain_text("<p>First &amp; second.</p><p>Next paragraph.</p>"), "First & second. Next paragraph.")
        self.assertEqual(plain_text("<h1>Heading</h1><div>First</div><div>Second</div>"), "Heading First Second")
        self.assertEqual(short_description("<p>Excerpt</p>", "Body"), "Excerpt")
        self.assertEqual(short_description("", "<p>Body</p>"), "Body")
        self.assertLessEqual(len(short_description("word " * 300, "")), 500)
        self.assertEqual(short_description("", ""), "")

    def test_shortening_preserves_word_boundaries(self):
        self.assertEqual(short_description("x" * 501, ""), "…")
        self.assertEqual(shorten("first second third", 13), "first second…")
        self.assertEqual(shorten("first second third", 12), "first…")

    def test_identity_map_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identities.json"
            expected = uuid4()
            path.write_text(json.dumps({"2": str(expected)}))
            self.assertEqual(load_identity_map(path), {2: expected})
            for value in ([str(expected)], {"0": str(expected)}, {"2": "invalid"}, {"2": str(expected), "3": str(expected)}):
                path.write_text(json.dumps(value))
                with self.assertRaises(CommandError):
                    load_identity_map(path)
