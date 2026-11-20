import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from review_auth import Role


class User(AbstractUser):
    class ApplicationRole(models.TextChoices):
        READER = Role.READER.value, "Reader"
        EDITOR = Role.EDITOR.value, "Editor"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    wordpress_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True)
    role = models.CharField(
        max_length=16,
        choices=ApplicationRole.choices,
        default=ApplicationRole.READER,
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(username__regex=r"\S"), name="auth_username_nonblank"
            ),
            models.CheckConstraint(
                condition=Q(wordpress_id__isnull=True) | Q(wordpress_id__gt=0),
                name="auth_wordpress_id_positive",
            ),
            models.CheckConstraint(
                condition=Q(role__in=[Role.READER.value, Role.EDITOR.value]),
                name="auth_role_valid",
            ),
        ]


class AccessToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="auth_token_expiry_after_creation",
            ),
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True) | Q(revoked_at__gte=F("created_at")),
                name="auth_token_revoked_after_creation",
            ),
        ]
