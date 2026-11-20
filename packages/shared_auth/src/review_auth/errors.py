"""Outcomes without service-specific HTTP status codes."""


class InvalidToken(Exception):
    """The credential is absent, inactive, revoked, or expired."""


class AuthUnavailable(Exception):
    """The lookup could not establish a trustworthy authentication result."""


class PermissionDenied(Exception):
    """An authenticated identity lacks the requested permission."""


def error_payload(code: str, message: str, **details: object) -> dict:
    return {"error": {"code": code, "message": message, **details}}
