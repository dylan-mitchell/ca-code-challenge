"""The wire contract for the two services' custom introspection protocol."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID

from .errors import AuthUnavailable


class Role(StrEnum):
    READER = "reader"
    EDITOR = "editor"


@dataclass(frozen=True)
class Identity:
    id: UUID
    username: str
    role: Role


@dataclass(frozen=True)
class VerifiedToken:
    user: Identity
    expires_at: datetime


def validate_result(value: object) -> VerifiedToken:
    """Validate values supplied by either a database or a network adapter."""
    if not isinstance(value, VerifiedToken) or not isinstance(value.user, Identity):
        raise AuthUnavailable("Invalid authentication result.")
    user = value.user
    if not isinstance(user.id, UUID) or not isinstance(user.username, str) or not user.username.strip():
        raise AuthUnavailable("Invalid authentication identity.")
    try:
        role = Role(user.role)
    except (TypeError, ValueError) as exc:
        raise AuthUnavailable("Unrecognized role.") from exc
    expiry = value.expires_at
    if not isinstance(expiry, datetime) or expiry.tzinfo is None or expiry.utcoffset() is None:
        raise AuthUnavailable("Invalid token expiration.")
    return VerifiedToken(Identity(user.id, user.username, role), expiry.astimezone(timezone.utc))


def encode_introspection(value: VerifiedToken | None) -> dict:
    if value is None:
        return {"active": False}
    value = validate_result(value)
    return {
        "active": True,
        "expires_at": value.expires_at.isoformat().replace("+00:00", "Z"),
        "user": {
            "id": str(value.user.id),
            "username": value.user.username,
            "role": value.user.role.value,
        },
    }


def parse_introspection(payload: object) -> VerifiedToken | None:
    """Reject unusable responses while tolerating additive response fields."""
    if not isinstance(payload, dict) or type(payload.get("active")) is not bool:
        raise AuthUnavailable("Invalid introspection response.")
    if not payload["active"]:
        return None
    try:
        user = payload["user"]
        if not isinstance(user, dict):
            raise ValueError("user must be an object")
        identifier = user["id"]
        expiry = payload["expires_at"]
        if not isinstance(identifier, str) or not isinstance(expiry, str):
            raise ValueError("invalid identity or expiry")
        value = VerifiedToken(
            Identity(UUID(identifier), user["username"], Role(user["role"])),
            datetime.fromisoformat(expiry.replace("Z", "+00:00")),
        )
        return validate_result(value)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AuthUnavailable("Invalid introspection response.") from exc
