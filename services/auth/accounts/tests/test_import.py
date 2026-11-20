import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import AccessToken, User
from accounts.wordpress import imported_role, parse_capabilities


def source_rows():
    return [
        {
            "wordpress_id": 1, "username": "admin", "email": "admin@example.com",
            "registered_at": datetime(2026, 5, 19, 12, 30),
            "capabilities": 'a:1:{s:13:"administrator";b:1;}',
        },
        {
            "wordpress_id": 2, "username": "sarah_k", "email": "sarah@example.com",
            "registered_at": datetime(2026, 5, 19, 13, 30),
            "capabilities": 'a:1:{s:10:"subscriber";b:1;}',
        },
    ]


class CapabilityTests(SimpleTestCase):
    def test_flat_php_boolean_map_and_role_mapping(self):
        self.assertEqual(imported_role(source_rows()[0]["capabilities"]), "editor")
        self.assertEqual(imported_role(source_rows()[1]["capabilities"]), "reader")
        self.assertEqual(parse_capabilities('a:1:{s:2:"é";b:0;}'), {"é": False})

    def test_malformed_or_executable_php_shapes_are_rejected(self):
        for serialized in [
            'O:4:"Evil":0:{}', 'a:1:{s:9:"subscriber";b:1;}',
            'a:1:{s:10:"subscriber";i:1;}', 'a:0:{}trailing',
            'a:2:{s:1:"x";b:1;s:1:"x";b:0;}', None,
        ]:
            with self.subTest(serialized=serialized), self.assertRaises(ValueError):
                parse_capabilities(serialized)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AccountImportTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "mapping.json"
        self.output = io.StringIO()

    def run_import(self, rows=None, password="local-demo-password"):
        with patch("accounts.management.commands.import_wordpress_users.read_source_users", return_value=rows or source_rows()):
            with patch.dict(os.environ, {"AUTH_IMPORT_PASSWORD": password}):
                call_command("import_wordpress_users", mapping_output=self.path, stdout=self.output)

    def test_import_preserves_source_identity_date_and_initial_role_without_admin_flags(self):
        self.run_import()
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(AccessToken.objects.count(), 0)
        admin = User.objects.get(wordpress_id=1)
        sarah = User.objects.get(wordpress_id=2)
        self.assertEqual(admin.role, "editor")
        self.assertFalse(admin.is_staff)
        self.assertFalse(admin.is_superuser)
        self.assertEqual(sarah.role, "reader")
        self.assertEqual(sarah.date_joined, datetime(2026, 5, 19, 13, 30, tzinfo=timezone.utc))
        self.assertTrue(sarah.check_password("local-demo-password"))
        self.assertEqual(json.loads(self.path.read_text()), {
            "1": str(admin.public_id), "2": str(sarah.public_id),
        })
        self.assertIn("created=2, existing=0", self.output.getvalue())
        self.assertNotIn("local-demo-password", self.output.getvalue() + self.path.read_text())

    def test_rerun_preserves_all_existing_fields_without_requiring_import_password(self):
        self.run_import()
        sarah = User.objects.get(wordpress_id=2)
        sarah.username = "renamed-local"
        sarah.email = "changed@example.com"
        sarah.role = "editor"
        sarah.is_active = False
        sarah.set_password("new local password")
        sarah.save()
        before = list(User.objects.order_by("id").values())
        mapping = self.path.read_text()
        self.run_import(password="")
        self.assertEqual(list(User.objects.order_by("id").values()), before)
        self.assertEqual(self.path.read_text(), mapping)
        self.assertIn("created=0, existing=2", self.output.getvalue())

    def test_invalid_later_row_rolls_back_the_whole_auth_phase(self):
        rows = source_rows()
        rows[1]["registered_at"] = "0000-00-00 00:00:00"
        with self.assertRaisesMessage(CommandError, "date_joined"):
            self.run_import(rows)
        self.assertEqual(User.objects.count(), 0)
        self.assertFalse(self.path.exists())
        self.assertNotIn("committed", self.output.getvalue())

    def test_username_collision_does_not_merge_native_account(self):
        native = User.objects.create(username="sarah_k")
        with self.assertRaisesMessage(CommandError, "username conflicts"):
            self.run_import()
        self.assertEqual(User.objects.count(), 1)
        native.refresh_from_db()
        self.assertIsNone(native.wordpress_id)
        self.assertFalse(self.path.exists())

    def test_missing_demo_password_fails_only_when_new_accounts_are_needed(self):
        with self.assertRaisesMessage(CommandError, "AUTH_IMPORT_PASSWORD"):
            self.run_import(password="")
        self.assertEqual(User.objects.count(), 0)

    def test_failed_mapping_export_keeps_committed_accounts_and_rerun_recovers(self):
        with patch("accounts.management.commands.import_wordpress_users.publish_mapping", side_effect=OSError("disk full")):
            with self.assertRaisesMessage(CommandError, "accounts were committed"):
                self.run_import()
        before = list(User.objects.order_by("id").values_list("public_id", flat=True))
        self.assertEqual(len(before), 2)
        self.assertFalse(self.path.exists())
        self.run_import(password="")
        self.assertEqual(list(User.objects.order_by("id").values_list("public_id", flat=True)), before)
        self.assertEqual(set(json.loads(self.path.read_text())), {"1", "2"})

    def test_duplicate_source_accounts_are_rejected_before_writes(self):
        rows = source_rows()
        rows.append(rows[0].copy())
        with self.assertRaisesMessage(CommandError, "duplicate"):
            self.run_import(rows)
        self.assertEqual(User.objects.count(), 0)
