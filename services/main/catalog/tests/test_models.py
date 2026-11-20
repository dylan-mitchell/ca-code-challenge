from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from catalog.models import Brand, Industry, Review
from .factories import brand, review, reviewer


class ModelTests(TestCase):
    def setUp(self):
        self.author = reviewer()
        self.brand = brand()
        self.review = review(self.brand, self.author)

    def test_multiple_reviews_and_empty_content_are_valid(self):
        another = review(self.brand, self.author, slug="another")
        another.full_clean()
        self.assertEqual(self.brand.reviews.count(), 2)
        self.assertEqual(self.brand.industries.count(), 0)

    def test_referenced_objects_are_protected(self):
        for record in (self.brand, self.author):
            with self.assertRaises(ProtectedError):
                record.delete()

    def test_selected_review_is_cleared_on_delete(self):
        self.brand.top_review = self.review
        self.brand.save(update_fields=["top_review"])
        self.review.delete()
        self.brand.refresh_from_db()
        self.assertIsNone(self.brand.top_review_id)

    def test_wrong_brand_selection_and_reparenting_are_rejected(self):
        other = brand("other")
        other.top_review = self.review
        with self.assertRaises(ValidationError):
            other.save()
        self.brand.top_review = self.review
        self.brand.save()
        self.review.brand = other
        with self.assertRaises(ValidationError):
            self.review.save()

    def test_database_constraints_reject_invalid_values(self):
        for updates in ({"rating": 0}, {"rating": 6}, {"wordpress_id": 0}, {"title": " \t "}, {"slug": ""}):
            with self.subTest(updates=updates), self.assertRaises(IntegrityError), transaction.atomic():
                Review.objects.filter(pk=self.review.pk).update(**updates)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Brand.objects.filter(pk=self.brand.pk).update(founded_year=1700)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Industry.objects.create(name=" ", slug="blank")

    def test_source_identity_and_slugs_are_unique(self):
        self.brand.wordpress_id = 7
        self.brand.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            brand("new", wordpress_id=7)
        with self.assertRaises(IntegrityError), transaction.atomic():
            brand("acme")

    def test_byline_fallback_tracks_profile_only_when_blank(self):
        self.assertEqual(self.review.display_name, "Sarah K.")
        self.review.reviewer_name = "A public byline"
        self.author.display_name = "New profile name"
        self.author.save()
        self.assertEqual(self.review.display_name, "A public byline")
