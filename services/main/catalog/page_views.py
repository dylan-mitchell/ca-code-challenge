from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_safe

from .models import Review
from .queries import brands_with_stats, listing_brands
from .serialization import review_snippet


@require_safe
def home(request):
    recent = Review.objects.select_related("brand", "reviewer").order_by("-published_at", "-id")[:6]
    return render(request, "catalog/home.html", {
        "brands": listing_brands()[:6],
        "recent_reviews": [{"review": review, "snippet": review_snippet(review)} for review in recent],
        "nav_section": "home",
    })


@require_safe
def brand_list(request):
    return render(request, "catalog/brand_list.html", {"nav_section": "brands"})


@require_safe
def brand_detail(request, slug):
    brand = get_object_or_404(brands_with_stats(), slug=slug)
    return render(request, "catalog/brand_detail.html", {
        "brand": brand,
        "reviews": brand.reviews.select_related("reviewer").order_by("-published_at", "-id"),
        "pick_snippet": review_snippet(brand.top_review) if brand.top_review else "",
        "nav_section": "brands",
    })


@require_safe
def review_detail(request, slug):
    review = get_object_or_404(Review.objects.select_related("brand", "reviewer"), slug=slug)
    return render(request, "catalog/review_detail.html", {"review": review, "nav_section": "brands"})
