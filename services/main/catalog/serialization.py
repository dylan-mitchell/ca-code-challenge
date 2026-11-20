from datetime import timezone

from .content import plain_text, shorten


def review_snippet(review):
    return shorten(plain_text(review.body_html) or review.title, 240)


def selected_review(review):
    if review is None:
        return None
    return {
        "id": str(review.pk), "slug": review.slug, "title": review.title,
        "rating": review.rating, "reviewer_name": review.display_name,
        "published_at": review.published_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "snippet": review_snippet(review),
    }


def brand_card(brand):
    return {
        "id": str(brand.pk), "name": brand.name, "slug": brand.slug,
        "industries": [{"slug": item.slug, "name": item.name} for item in brand.industries.all()],
        "average_rating": round(float(brand.average_rating), 2) if brand.average_rating is not None else None,
        "review_count": brand.review_count, "short_description": brand.short_description,
        "top_review": selected_review(brand.top_review),
    }
