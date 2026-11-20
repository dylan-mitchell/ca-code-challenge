from uuid import uuid4
from django.utils import timezone
from catalog.models import Brand, Review, Reviewer


def reviewer(**kwargs):
    return Reviewer.objects.create(auth_user_id=uuid4(), display_name="Sarah K.", **kwargs)


def brand(slug="acme", **kwargs):
    return Brand.objects.create(slug=slug, name=slug.title(), **kwargs)


def review(brand, reviewer, slug="review", **kwargs):
    values = {"title": "A useful review", "rating": 5, "published_at": timezone.now()}
    values.update(kwargs)
    return Review.objects.create(brand=brand, reviewer=reviewer, slug=slug, **values)
