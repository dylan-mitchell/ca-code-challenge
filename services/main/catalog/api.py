import json
import re

from django.core.exceptions import RequestDataTooBig
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from review_auth import AuthUnavailable, InvalidToken, PermissionDenied, error_payload, require_editor, verify_token

from .auth_client import introspection_lookup
from .models import Brand, Industry, Review
from .queries import brands_with_stats, listing_brands
from .serialization import brand_card

SORTS = {"average_rating", "-average_rating", "review_count", "-review_count"}


def error(code, message, status=400, **details):
    return JsonResponse(error_payload(code, message, **details), status=status)


def method_error(allowed):
    response = error("method_not_allowed", "Method not allowed.", status=405)
    response["Allow"] = allowed
    return response


def positive_number(value):
    if not isinstance(value, str) or len(value) > 19 or not re.fullmatch(r"[0-9]+", value):
        raise ValueError
    result = int(value)
    if result < 1:
        raise ValueError
    return result


def invalid_json_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def brand_list(request):
    if request.method != "GET":
        return method_error("GET")
    for name in ("sort", "page", "page_size"):
        if len(request.GET.getlist(name)) > 1:
            return error(f"invalid_{name}", "Supply this parameter once.", parameter=name)
    sort = request.GET.get("sort", "-average_rating")
    if sort not in SORTS:
        return error("invalid_sort", "Unsupported sort value.", parameter="sort")
    numbers = {}
    for name, default in (("page", "1"), ("page_size", "20")):
        try:
            numbers[name] = positive_number(request.GET.get(name, default))
        except ValueError:
            return error(f"invalid_{name}", "Use a positive integer.", parameter=name)
    if numbers["page_size"] > 100:
        return error("invalid_page_size", "Page size must be between 1 and 100.", parameter="page_size")
    industries = list(Industry.objects.values("slug", "name"))
    selected = list(dict.fromkeys(request.GET.getlist("industry")))
    if set(selected) - {item["slug"] for item in industries}:
        return error("invalid_industry", "Unknown industry slug.", parameter="industry")
    paginator = Paginator(listing_brands(selected, sort), numbers["page_size"])
    try:
        page = paginator.page(numbers["page"])
    except EmptyPage:
        return error("page_not_found", "That result page does not exist.", status=404, parameter="page")

    def page_url(number):
        query = request.GET.copy()
        query["page"] = str(number)
        return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")

    return JsonResponse({
        "count": paginator.count,
        "next": page_url(page.next_page_number()) if page.has_next() else None,
        "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
        "results": [brand_card(brand) for brand in page],
        "available_industries": industries,
    })


def authenticate_editor(request):
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        response = error("authentication_required", "A bearer token is required.", status=401)
        response["WWW-Authenticate"] = "Bearer"
        return response
    try:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise InvalidToken("Invalid bearer credentials.")
        verified = verify_token(parts[1], lookup=introspection_lookup)
        require_editor(verified.user)
    except InvalidToken:
        response = error("invalid_token", "The bearer token is invalid or inactive.", status=401)
        response["WWW-Authenticate"] = 'Bearer error="invalid_token"'
        return response
    except PermissionDenied:
        return error("permission_denied", "The editor role is required.", status=403)
    except AuthUnavailable:
        return error("auth_unavailable", "Authentication is temporarily unavailable.", status=503)
    return None


@csrf_exempt  # This endpoint accepts explicit bearer credentials, never cookie sessions.
def brand_update(request, slug):
    if request.method != "PATCH":
        return method_error("PATCH")
    rejection = authenticate_editor(request)
    if rejection is not None:
        return rejection
    if request.content_type.lower() != "application/json":
        return error("unsupported_media_type", "Use application/json.", status=415)
    try:
        data = json.loads(request.body.decode("utf-8"), parse_constant=invalid_json_constant)
    except RequestDataTooBig:
        return error("invalid_request", "The request body is too large.")
    except (ValueError, UnicodeError):
        return error("invalid_json", "Body must contain valid JSON.")
    if not isinstance(data, dict) or not data:
        return error("invalid_request", "Provide an object with at least one update field.")
    fields = {}

    def invalid(field, code, message):
        fields.setdefault(field, []).append({"code": code, "message": message})

    for field in data.keys() - {"short_description", "top_review_id"}:
        invalid(field, "unknown_field", "This field cannot be updated.")
    if "short_description" in data:
        description = data["short_description"]
        if not isinstance(description, str) or len(description) > 500:
            invalid("short_description", "invalid_value", "Use a text string of at most 500 characters.")
        else:
            try:
                description.encode("utf-8")
                if "\x00" in description:
                    raise ValueError
            except (UnicodeError, ValueError):
                invalid("short_description", "invalid_value", "Use valid Unicode text without null characters.")
    selected_id = data.get("top_review_id")
    if selected_id is not None:
        try:
            selected_id = positive_number(selected_id)
            if selected_id > 9223372036854775807:
                raise ValueError
        except ValueError:
            invalid("top_review_id", "invalid_selection", "Select an existing review belonging to this brand.")
    if fields:
        return error("validation_error", "One or more fields are invalid.", fields=fields)
    with transaction.atomic():
        try:
            brand = Brand.objects.select_for_update().get(slug=slug)
        except Brand.DoesNotExist:
            return error("brand_not_found", "Brand not found.", status=404)
        if selected_id is not None and not Review.objects.select_for_update().filter(pk=selected_id, brand=brand).exists():
            invalid("top_review_id", "invalid_selection", "Select an existing review belonging to this brand.")
            return error("validation_error", "One or more fields are invalid.", fields=fields)
        changes = {}
        if "short_description" in data:
            changes["short_description"] = data["short_description"]
        if "top_review_id" in data:
            changes["top_review_id"] = selected_id
        Brand.objects.filter(pk=brand.pk).update(**changes)
        return JsonResponse(brand_card(brands_with_stats().get(pk=brand.pk)))
