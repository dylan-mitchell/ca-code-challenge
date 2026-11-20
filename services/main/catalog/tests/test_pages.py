import json
import tempfile
import uuid
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from catalog.models import Brand, Industry, Review, Reviewer


class ViteAssetTests(SimpleTestCase):
    @override_settings(VITE_DEV_SERVER_URL="http://localhost:5173")
    def test_development_css_does_not_depend_on_javascript(self):
        html = Template("{% load vite %}{% vite_css 'scss/main.scss' %}").render(Context())
        self.assertIn('href="http://localhost:5173/scss/main.scss?direct"', html)
        self.assertNotIn("script", html)

    @override_settings(VITE_DEV_SERVER_URL="http://localhost:5173")
    def test_development_react_refresh_preamble(self):
        html = Template("{% load vite %}{% vite_js 'src/main.tsx' %}").render(Context())
        self.assertIn("@react-refresh", html)
        self.assertIn("__vite_plugin_react_preamble_installed__", html)
        self.assertIn('src="http://localhost:5173/src/main.tsx"', html)

    @override_settings(VITE_DEV_SERVER_URL="")
    def test_production_assets_include_nested_dependencies_once(self):
        manifest = {
            "scss/main.scss": {"file": "assets/styles.css"},
            "src/main.tsx": {"file": "assets/listing.js", "css": ["assets/styles.css"], "imports": ["chunk"]},
            "chunk": {"file": "assets/shared.js", "css": ["assets/shared.css"], "imports": ["nested"]},
            "nested": {"file": "assets/nested.js", "css": ["assets/shared.css"]},
        }
        with tempfile.TemporaryDirectory() as directory, override_settings(FRONTEND_DIST=Path(directory)):
            (Path(directory) / "manifest.json").write_text(json.dumps(manifest))
            html = Template("{% load vite %}{% vite_css 'scss/main.scss' %}{% vite_js 'src/main.tsx' %}").render(Context())
        self.assertEqual(html.count("assets/styles.css"), 1)
        self.assertEqual(html.count("assets/shared.css"), 1)
        self.assertIn('rel="modulepreload" href="/static/frontend/assets/nested.js"', html)
        self.assertIn('src="/static/frontend/assets/listing.js"', html)

    @override_settings(VITE_DEV_SERVER_URL="")
    def test_missing_build_has_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(FRONTEND_DIST=Path(directory)):
            with self.assertRaisesMessage(ImproperlyConfigured, "npm run build"):
                Template("{% load vite %}{% vite_css 'scss/main.scss' %}").render(Context())


@override_settings(VITE_DEV_SERVER_URL="http://localhost:5173")
class PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name="Acme", slug="acme-original", description_html="<p>Useful <strong>information</strong>.</p>", short_description="Simple choices.")
        cls.industry = Industry.objects.create(name="Insurance", slug="insurance")
        cls.brand.industries.add(cls.industry)
        cls.reviewer = Reviewer.objects.create(auth_user_id=uuid.uuid4(), display_name="Sarah")
        cls.review = Review.objects.create(brand=cls.brand, reviewer=cls.reviewer, title="A helpful experience", slug="original-review", rating=4, published_at=timezone.now(), body_html="<p>Details worth reading.</p>")
        Review.objects.create(brand=cls.brand, reviewer=cls.reviewer, title="A different view", slug="different-view", rating=2, published_at=timezone.now(), reviewer_name="Sam")

    def test_homepage_is_server_rendered_and_has_no_react_bundle(self):
        response = self.client.get("/")
        self.assertContains(response, "Top-rated brands")
        self.assertContains(response, "Recent reviews")
        self.assertContains(response, "3.00")
        self.assertContains(response, '/brand/acme-original/')
        self.assertContains(response, '/review/original-review/')
        self.assertNotContains(response, "src/main.tsx")

    def test_directory_alone_mounts_react_and_explains_javascript(self):
        response = self.client.get("/brand/")
        self.assertContains(response, 'id="brand-list"')
        self.assertContains(response, "src/main.tsx")
        self.assertContains(response, "<noscript>")

    def test_brand_detail_uses_derived_rating_all_reviews_and_no_automatic_pick(self):
        response = self.client.get("/brand/acme-original/")
        self.assertContains(response, "3.00")
        self.assertContains(response, "Insurance")
        self.assertContains(response, "<strong>information</strong>", html=True)
        self.assertContains(response, "Sarah")
        self.assertContains(response, "Sam")
        self.assertNotContains(response, "Editor's pick")
        self.assertNotContains(response, "src/main.tsx")

    def test_explicit_pick_is_displayed(self):
        self.brand.top_review = self.review
        self.brand.save(update_fields=["top_review"])
        self.assertContains(self.client.get("/brand/acme-original/"), "Editor's pick")

    def test_review_detail_retains_semantic_body_and_name_fallback(self):
        response = self.client.get("/review/original-review/")
        self.assertContains(response, "Sarah")
        self.assertContains(response, "<p>Details worth reading.</p>", html=True)
        self.assertContains(response, '/brand/acme-original/')
        self.assertNotContains(response, "src/main.tsx")

    def test_empty_body_and_unrated_brand_are_valid(self):
        response = self.client.get("/review/different-view/")
        self.assertContains(response, "Sam")
        Brand.objects.create(name="New brand", slug="new-brand")
        self.assertContains(self.client.get("/brand/new-brand/"), "Not rated yet")

    def test_unknown_slugs_return_404(self):
        self.assertEqual(self.client.get("/brand/missing/").status_code, 404)
        self.assertEqual(self.client.get("/review/missing/").status_code, 404)
