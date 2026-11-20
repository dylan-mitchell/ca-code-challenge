from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import AccessToken, User


class SchemaTests(TestCase):
    def test_native_accounts_may_share_null_source_ids_and_email(self):
        first = User.objects.create_user("first", email="same@example.com")
        second = User.objects.create_user("second", email="same@example.com")
        self.assertNotEqual(first.public_id, second.public_id)
        self.assertIsNone(first.wordpress_id)
        self.assertEqual(first.role, "reader")

    def test_database_rejects_invalid_identity_and_role_values(self):
        for values in [
            {"username": " "},
            {"username": "zero", "wordpress_id": 0},
            {"username": "owner", "role": "owner"},
        ]:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.create(**values)

    def test_source_ids_and_public_ids_are_unique(self):
        user = User.objects.create(username="first", wordpress_id=1)
        for values in [{"wordpress_id": 1}, {"public_id": user.public_id}]:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.create(username="second", **values)

    def test_token_time_constraints_and_local_cascade(self):
        user = User.objects.create(username="token-owner")
        now = timezone.now()
        for values in [
            {"expires_at": now},
            {"expires_at": now + timedelta(hours=1), "revoked_at": now - timedelta(seconds=1)},
        ]:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                AccessToken.objects.create(user=user, token_digest="a" * 64, created_at=now, **values)
        AccessToken.objects.create(
            user=user, token_digest="b" * 64, created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        user.delete()
        self.assertEqual(AccessToken.objects.count(), 0)
