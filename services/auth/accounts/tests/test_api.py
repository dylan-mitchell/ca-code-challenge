import base64
from datetime import timedelta
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import AccessToken, User
from accounts.operations import (
    change_password, change_role, revoke_all_tokens, revoke_token,
    set_user_active, token_digest,
)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    INTROSPECTION_CLIENT_ID="main-app",
    INTROSPECTION_CLIENT_SECRET="test-service-secret",
    TOKEN_TTL_SECONDS=3600,
)
class AuthAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sarah_k", password=" correct password ", role="editor")
        self.basic = "Basic " + base64.b64encode(b"main-app:test-service-secret").decode()

    def login(self, **overrides):
        return self.client.post(
            "/api/login/", {"username": "sarah_k", "password": " correct password ", **overrides},
            content_type="application/json",
        )

    def introspect(self, token, **overrides):
        return self.client.post(
            "/api/tokens/introspect/", {"token": token}, content_type="application/json",
            HTTP_AUTHORIZATION=overrides.pop("authorization", self.basic), **overrides,
        )

    def test_login_issues_multiple_hashed_one_hour_tokens(self):
        first = self.login()
        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertEqual(
            set(payload), {"access_token", "token_type", "expires_in", "expires_at", "user"}
        )
        self.assertEqual(payload["user"], {
            "id": str(self.user.public_id), "username": "sarah_k", "role": "editor"
        })
        self.assertEqual(payload["token_type"], "Bearer")
        self.assertEqual(payload["expires_in"], 3600)
        self.assertTrue(payload["expires_at"].endswith("Z"))
        self.assertEqual(first["Cache-Control"], "no-store")
        token = AccessToken.objects.get()
        self.assertEqual(token.token_digest, token_digest(payload["access_token"]))
        self.assertNotEqual(token.token_digest, payload["access_token"])
        self.assertEqual(token.expires_at - token.created_at, timedelta(hours=1))
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

        second = self.login().json()["access_token"]
        self.assertNotEqual(second, payload["access_token"])
        self.assertEqual(AccessToken.objects.count(), 2)
        self.assertTrue(self.introspect(payload["access_token"]).json()["active"])
        self.assertTrue(self.introspect(second).json()["active"])

    def test_password_is_not_trimmed_and_bad_credentials_are_indistinguishable(self):
        wrong = self.login(password="correct password")
        missing_user = self.login(username="unknown")
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        disabled = self.login()
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json()["error"]["code"], "invalid_credentials")
        self.assertEqual(wrong.json(), missing_user.json())
        self.assertEqual(wrong.json(), disabled.json())
        self.assertEqual(AccessToken.objects.count(), 0)

    def test_login_strict_json_validation(self):
        cases = [
            ("{", 400, "invalid_json"),
            ("[]", 400, "invalid_request"),
            ("{}", 400, "validation_error"),
            ('{"username": "sarah_k", "password": true}', 400, "validation_error"),
            ('{"username": "sarah_k", "password": "x", "role": "editor"}', 400, "validation_error"),
            ('{"username": "sarah\\u0000", "password": "x"}', 400, "validation_error"),
            ('{"username": "sarah_k", "password": "\\ud800"}', 400, "validation_error"),
            ('{"username": "sarah_k", "password": NaN}', 400, "invalid_json"),
        ]
        for body, status, code in cases:
            with self.subTest(body=body):
                response = self.client.post("/api/login/", body, content_type="application/json")
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], code)
                self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(self.client.post("/api/login/", {}).status_code, 415)
        self.assertEqual(self.client.get("/api/login/").status_code, 405)

    def test_introspection_requires_the_service_credential(self):
        token = self.login().json()["access_token"]
        for authorization in ["", f"Bearer {token}", "Basic !!!", "Basic bm86bm8=", "Basic /w=="]:
            with self.subTest(authorization=authorization):
                response = self.introspect(token, authorization=authorization)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["error"]["code"], "invalid_client")
                self.assertEqual(response["WWW-Authenticate"], 'Basic realm="auth-introspection"')
                self.assertEqual(response["Cache-Control"], "no-store")

    def test_introspection_validation_and_inactive_shape(self):
        for body in [{}, {"token": None}, {"token": ""}, {"token": 1}, {"token": "x", "extra": 1}]:
            with self.subTest(body=body):
                response = self.client.post(
                    "/api/tokens/introspect/", body, content_type="application/json",
                    HTTP_AUTHORIZATION=self.basic,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "validation_error")
        response = self.introspect("unknown-nonempty-token")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"active": False})

    def test_introspection_reads_current_role_and_does_not_extend_or_login(self):
        raw = self.login().json()["access_token"]
        stored = AccessToken.objects.get()
        self.user.refresh_from_db()
        last_login = self.user.last_login
        change_role(self.user, "reader")
        # A superuser flag is not the application's editor role.
        User.objects.filter(pk=self.user.pk).update(is_staff=True, is_superuser=True)
        response = self.introspect(raw)
        self.assertTrue(response.json()["active"])
        self.assertEqual(response.json()["user"]["role"], "reader")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.user.refresh_from_db()
        stored.refresh_from_db()
        self.assertEqual(self.user.last_login, last_login)
        self.assertEqual(AccessToken.objects.count(), 1)
        self.assertIsNone(stored.revoked_at)

    def test_expired_token_row_remains_but_is_inactive(self):
        raw = self.login().json()["access_token"]
        now = timezone.now()
        AccessToken.objects.update(
            created_at=now - timedelta(hours=2), expires_at=now - timedelta(seconds=1)
        )
        self.assertEqual(self.introspect(raw).json(), {"active": False})
        self.assertEqual(AccessToken.objects.count(), 1)

    def test_single_token_revocation_does_not_revoke_other_logins(self):
        first = self.login().json()["access_token"]
        second = self.login().json()["access_token"]
        token = AccessToken.objects.get(token_digest=token_digest(first))
        self.assertTrue(revoke_token(token))
        self.assertFalse(revoke_token(token))
        self.assertEqual(self.introspect(first).json(), {"active": False})
        self.assertTrue(self.introspect(second).json()["active"])
        self.assertEqual(revoke_all_tokens(self.user), 1)
        self.assertEqual(self.introspect(second).json(), {"active": False})

    def test_disable_and_reenable_does_not_revive_tokens(self):
        raws = [self.login().json()["access_token"] for _ in range(2)]
        set_user_active(self.user, False)
        self.assertFalse(AccessToken.objects.filter(revoked_at__isnull=True).exists())
        set_user_active(self.user, True)
        for raw in raws:
            self.assertEqual(self.introspect(raw).json(), {"active": False})
        self.assertEqual(self.login().status_code, 200)

    def test_password_change_revokes_all_tokens(self):
        raw = self.login().json()["access_token"]
        change_password(self.user, "replacement password")
        self.assertEqual(self.introspect(raw).json(), {"active": False})
        self.assertEqual(self.login().status_code, 400)
        self.assertEqual(self.login(password="replacement password").status_code, 200)

    def test_account_change_and_revocation_roll_back_together(self):
        raw = self.login().json()["access_token"]
        with patch("accounts.operations._revoke_all", side_effect=OperationalError("unavailable")):
            with self.assertRaises(OperationalError):
                change_password(self.user, "should not be stored")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(" correct password "))
        self.assertTrue(self.introspect(raw).json()["active"])

    def test_infrastructure_failure_is_not_inactive(self):
        with patch("accounts.operations.AccessToken.objects.select_related", side_effect=OperationalError("down")):
            response = self.introspect("token")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "auth_unavailable")
        with patch("accounts.operations.User.objects.select_for_update", side_effect=OperationalError("down")):
            response = self.login()
        self.assertEqual(response.status_code, 503)
        with self.settings(INTROSPECTION_CLIENT_SECRET=""):
            self.assertEqual(self.introspect("token").status_code, 503)
