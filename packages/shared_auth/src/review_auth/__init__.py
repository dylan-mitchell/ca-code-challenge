"""Pure Python contracts; database and HTTP lookups belong to the caller."""

from .contracts import Identity, Role, VerifiedToken, encode_introspection, parse_introspection
from .errors import AuthUnavailable, InvalidToken, PermissionDenied, error_payload
from .verification import require_editor, verify_token

__all__ = [
    "AuthUnavailable", "Identity", "InvalidToken", "PermissionDenied", "Role",
    "VerifiedToken", "encode_introspection", "error_payload", "parse_introspection",
    "require_editor", "verify_token",
]
