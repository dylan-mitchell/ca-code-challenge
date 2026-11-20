"""Small JSON endpoints; HTTP status decisions stay outside review_auth."""

import base64
import binascii
import json
import secrets
from functools import wraps

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from review_auth import AuthUnavailable, InvalidToken, encode_introspection, error_payload, verify_token

from .operations import InvalidCredentials, authenticate_and_issue, lookup_token


def failure(code, message, status=400, **details):
    return JsonResponse(error_payload(code, message, **details), status=status)


def json_endpoint(view):
    @csrf_exempt
    @wraps(view)
    def wrapped(request):
        if request.method != "POST":
            response = failure("method_not_allowed", "Use POST for this endpoint.", 405)
            response["Allow"] = "POST"
        else:
            try:
                response = view(request)
            except (AuthUnavailable, DatabaseError):
                response = failure(
                    "auth_unavailable", "Authentication is temporarily unavailable.", 503
                )
            except RequestDataTooBig:
                response = failure("invalid_request", "The request body is too large.")
        response["Cache-Control"] = "no-store"
        return response

    return wrapped


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def read_json(request):
    if request.content_type.lower() != "application/json":
        return None, failure("unsupported_media_type", "Send application/json.", 415)
    try:
        body = json.loads(request.body.decode("utf-8"), parse_constant=_invalid_constant)
    except (UnicodeDecodeError, ValueError):
        return None, failure("invalid_json", "The request body must contain valid JSON.")
    if not isinstance(body, dict):
        return None, failure("invalid_request", "The request body must be a JSON object.")
    return body, None


def required_strings(body, names):
    fields = {}
    for name in body.keys() - set(names):
        fields[name] = [{"code": "unsupported_field", "message": "This field is not supported."}]
    for name in names:
        if name not in body:
            fields[name] = [{"code": "required", "message": "This field is required."}]
        elif not isinstance(body[name], str) or body[name] == "":
            fields[name] = [{"code": "invalid", "message": "Provide a nonempty string."}]
        else:
            try:
                body[name].encode("utf-8")
            except UnicodeEncodeError:
                fields[name] = [{"code": "invalid", "message": "Provide valid Unicode text."}]
    if fields:
        return failure("validation_error", "One or more fields are invalid.", fields=fields)
    return None


@json_endpoint
def login(request):
    body, error = read_json(request)
    if error is not None:
        return error
    error = required_strings(body, ("username", "password"))
    if error is not None:
        return error
    if "\x00" in body["username"]:
        return failure(
            "validation_error", "One or more fields are invalid.",
            fields={"username": [{"code": "invalid", "message": "Provide a valid username."}]},
        )
    try:
        token, verified = authenticate_and_issue(body["username"], body["password"])
    except InvalidCredentials:
        return failure("invalid_credentials", "Invalid username or password.")
    encoded = encode_introspection(verified)
    return JsonResponse(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": settings.TOKEN_TTL_SECONDS,
            "expires_at": encoded["expires_at"],
            "user": encoded["user"],
        }
    )


def valid_service_credential(request):
    expected_id = settings.INTROSPECTION_CLIENT_ID
    expected_secret = settings.INTROSPECTION_CLIENT_SECRET
    if not expected_id or not expected_secret:
        raise AuthUnavailable("Introspection service credentials are not configured.")
    authorization = request.headers.get("Authorization", "")
    pieces = authorization.split()
    if len(pieces) != 2 or pieces[0].lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(pieces[1], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    client_id, separator, secret = decoded.partition(":")
    id_matches = secrets.compare_digest(client_id.encode(), expected_id.encode())
    secret_matches = secrets.compare_digest(secret.encode(), expected_secret.encode())
    return bool(separator and (id_matches & secret_matches))


@json_endpoint
def introspect(request):
    if not valid_service_credential(request):
        response = failure("invalid_client", "Service authentication failed.", 401)
        response["WWW-Authenticate"] = 'Basic realm="auth-introspection"'
        return response
    body, error = read_json(request)
    if error is not None:
        return error
    error = required_strings(body, ("token",))
    if error is not None:
        return error
    try:
        result = verify_token(body["token"], lookup=lookup_token)
    except InvalidToken:
        result = None
    return JsonResponse(encode_introspection(result))
