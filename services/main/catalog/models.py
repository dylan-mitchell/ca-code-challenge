from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.db.models import Q

from .validators import nonblank


class SourceRecord(models.Model):
    wordpress_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True)

    class Meta:
        abstract = True
        constraints = [models.CheckConstraint(
            condition=Q(wordpress_id__isnull=True) | Q(wordpress_id__gt=0),
            name="%(app_label)s_%(class)s_positive_wp_id",
        )]


class Industry(SourceRecord):
    name = models.CharField(max_length=200, validators=[nonblank])
    slug = models.SlugField(max_length=200, unique=True, validators=[nonblank])

    class Meta(SourceRecord.Meta):
        ordering = ["name", "id"]
        constraints = SourceRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="industry_nonblank_name"),
            models.CheckConstraint(condition=Q(slug__regex=r"\S"), name="industry_nonblank_slug"),
        ]

    def __str__(self):
        return self.name


class Reviewer(SourceRecord):
    auth_user_id = models.UUIDField(unique=True)
    display_name = models.CharField(max_length=250, validators=[nonblank])

    class Meta(SourceRecord.Meta):
        constraints = SourceRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(display_name__regex=r"\S"), name="reviewer_nonblank_name"),
        ]

    def __str__(self):
        return self.display_name


class Brand(SourceRecord):
    name = models.CharField(max_length=200, validators=[nonblank])
    slug = models.SlugField(max_length=200, unique=True, validators=[nonblank])
    description_html = models.TextField(blank=True, default="")
    short_description = models.CharField(max_length=500, blank=True, default="")
    website_url = models.URLField(max_length=2048, blank=True, default="", validators=[URLValidator(schemes=["http", "https"])])
    founded_year = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1800), MaxValueValidator(2100)])
    headquarters = models.CharField(max_length=200, blank=True, default="")
    industries = models.ManyToManyField(Industry, blank=True, related_name="brands")
    top_review = models.ForeignKey("Review", null=True, blank=True, on_delete=models.SET_NULL, related_name="selected_by_brands")

    class Meta(SourceRecord.Meta):
        ordering = ["name", "id"]
        constraints = SourceRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="brand_nonblank_name"),
            models.CheckConstraint(condition=Q(slug__regex=r"\S"), name="brand_nonblank_slug"),
            models.CheckConstraint(condition=Q(founded_year__isnull=True) | Q(founded_year__gte=1800, founded_year__lte=2100), name="brand_founded_year_range"),
        ]

    def clean(self):
        super().clean()
        if self.top_review_id and not Review.objects.filter(pk=self.top_review_id, brand_id=self.pk).exists():
            raise ValidationError({"top_review": "Select a review belonging to this brand."})

    def save(self, *args, **kwargs):
        # Guard ordinary model writes as well as the explicit API write path.
        if self.top_review_id:
            self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Review(SourceRecord):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(Reviewer, on_delete=models.PROTECT, related_name="reviews")
    title = models.CharField(max_length=250, validators=[nonblank])
    slug = models.SlugField(max_length=200, unique=True, validators=[nonblank])
    body_html = models.TextField(blank=True, default="")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    published_at = models.DateTimeField()
    reviewer_name = models.CharField(max_length=250, blank=True, default="")
    reviewer_location = models.CharField(max_length=200, blank=True, default="")

    class Meta(SourceRecord.Meta):
        ordering = ["-published_at", "-id"]
        constraints = SourceRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(title__regex=r"\S"), name="review_nonblank_title"),
            models.CheckConstraint(condition=Q(slug__regex=r"\S"), name="review_nonblank_slug"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_range"),
        ]

    @property
    def display_name(self):
        return self.reviewer_name if self.reviewer_name.strip() else self.reviewer.display_name

    def clean(self):
        super().clean()
        if self.pk and Brand.objects.filter(top_review_id=self.pk).exclude(pk=self.brand_id).exists():
            raise ValidationError({"brand": "A selected review cannot move to another brand."})

    def save(self, *args, **kwargs):
        if self.pk:
            self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title
