"""Authentication and permissions independent of Django, storage, and transport."""

from collections.abc import Callable
from datetime import datetime, timezone

from .contracts import Identity, Role, VerifiedToken, validate_result
from .errors import AuthUnavailable, InvalidToken, PermissionDenied


def verify_token(
    token: str,
    lookup: Callable[[str], VerifiedToken | None],
    *,
    now: datetime | None = None,
) -> VerifiedToken:
    if not isinstance(token, str) or not token.strip():
        raise InvalidToken("Missing token.")
    try:
        result = lookup(token)
    except (InvalidToken, AuthUnavailable):
        raise
    except Exception as exc:
        raise AuthUnavailable("Authentication lookup failed.") from exc
    if result is None:
        raise InvalidToken("Inactive token.")
    result = validate_result(result)
    if result.expires_at <= (now or datetime.now(timezone.utc)):
        raise InvalidToken("Expired token.")
    return result


def require_editor(identity: Identity) -> None:
    if identity.role != Role.EDITOR:
        raise PermissionDenied("Editor permission is required.")
