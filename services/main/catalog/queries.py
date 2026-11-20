from django.db.models import Avg, Count, F

from .models import Brand


def brands_with_stats():
    return Brand.objects.annotate(
        average_rating=Avg("reviews__rating"), review_count=Count("reviews"),
    ).select_related("top_review__reviewer").prefetch_related("industries")


def listing_brands(industries=(), sort="-average_rating"):
    brands = brands_with_stats()
    if industries:
        # A subquery keeps the industry join outside the review aggregation.
        matched_ids = Brand.objects.filter(industries__slug__in=industries).values("pk")
        brands = brands.filter(pk__in=matched_ids)
    metric = F(sort.lstrip("-"))
    ordering = metric.desc(nulls_last=True) if sort.startswith("-") else metric.asc(nulls_last=True)
    return brands.order_by(ordering, "name", "id")
