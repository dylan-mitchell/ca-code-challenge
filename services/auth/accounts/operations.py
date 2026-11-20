"""Auth-owned operations, also callable from Django's shell.

Account operations lock the user row, as does login. A concurrent login cannot
issue a token between a password/active-state change and its token revocation.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone
from review_auth import AuthUnavailable, Identity, Role, VerifiedToken

from .models import AccessToken, User


class InvalidCredentials(Exception):
    pass


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def identity_for_user(user: User) -> Identity:
    try:
        role = Role(user.role)
    except ValueError as exc:
        raise AuthUnavailable("Account has an unsupported role.") from exc
    return Identity(id=user.public_id, username=user.username, role=role)


def authenticate_and_issue(username: str, password: str) -> tuple[str, VerifiedToken]:
    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(username=username)
        except User.DoesNotExist:
            # Match the expensive password work for an unknown username too.
            User().set_password(password)
            raise InvalidCredentials from None
        password_matches = user.check_password(password)
        if not password_matches or not user.is_active:
            raise InvalidCredentials

        identity = identity_for_user(user)
        now = timezone.now()
        expires_at = now + timedelta(seconds=settings.TOKEN_TTL_SECONDS)
        raw_token = secrets.token_urlsafe(32)
        AccessToken.objects.create(
            user=user,
            token_digest=token_digest(raw_token),
            created_at=now,
            expires_at=expires_at,
        )
        user.last_login = now
        user.save(update_fields=["last_login"])
        return raw_token, VerifiedToken(user=identity, expires_at=expires_at)


def lookup_token(token: str) -> VerifiedToken | None:
    """Resolve opaque credentials locally; shared verification checks expiry."""
    try:
        stored = (
            AccessToken.objects.select_related("user")
            .filter(token_digest=token_digest(token))
            .first()
        )
        if stored is None or stored.revoked_at is not None or not stored.user.is_active:
            return None
        return VerifiedToken(
            user=identity_for_user(stored.user), expires_at=stored.expires_at
        )
    except DatabaseError as exc:
        raise AuthUnavailable("Token lookup is unavailable.") from exc


def _user_id(user: User | int) -> int:
    return user.pk if isinstance(user, User) else user


def revoke_token(token: AccessToken | int) -> bool:
    token_id = token.pk if isinstance(token, AccessToken) else token
    return bool(
        AccessToken.objects.filter(pk=token_id, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
    )


def _revoke_all(user_id: int) -> int:
    return AccessToken.objects.filter(user_id=user_id, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )


def revoke_all_tokens(user: User | int) -> int:
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=_user_id(user))
        return _revoke_all(locked.pk)


def set_user_active(user: User | int, active: bool) -> None:
    if not isinstance(active, bool):
        raise ValueError("active must be a boolean")
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=_user_id(user))
        locked.is_active = active
        locked.save(update_fields=["is_active"])
        if not active:
            _revoke_all(locked.pk)


def change_password(user: User | int, password: str) -> None:
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a nonempty string")
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=_user_id(user))
        locked.set_password(password)
        locked.save(update_fields=["password"])
        _revoke_all(locked.pk)


def change_role(user: User | int, role: Role | str) -> None:
    current_role = Role(role)
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=_user_id(user))
        locked.role = current_role.value
        locked.save(update_fields=["role"])
