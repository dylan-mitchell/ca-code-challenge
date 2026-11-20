import json
from datetime import timedelta
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from review_auth import AuthUnavailable

from catalog.auth_client import introspection_lookup


class Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def read(self, limit):
        return self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@override_settings(INTROSPECTION_CLIENT_ID="main-app", INTROSPECTION_CLIENT_SECRET="test-service-secret", AUTH_INTROSPECTION_URL="http://auth/api/tokens/introspect/", AUTH_TIMEOUT_SECONDS=2)
class AuthClientTests(SimpleTestCase):
    def test_sends_service_credential_and_token_separately(self):
        payload = {"active": True, "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(), "user": {"id": str(uuid4()), "username": "editor", "role": "editor"}}
        with patch("catalog.auth_client._opener.open", return_value=Response(json.dumps(payload).encode())) as opener:
            result = introspection_lookup("user-token")
        self.assertEqual(result.user.username, "editor")
        request = opener.call_args.args[0]
        self.assertEqual(json.loads(request.data), {"token": "user-token"})
        self.assertTrue(request.get_header("Authorization").startswith("Basic "))
        self.assertEqual(opener.call_args.kwargs["timeout"], 2)

    def test_inactive_is_distinct_from_errors(self):
        with patch("catalog.auth_client._opener.open", return_value=Response(b'{"active":false}')):
            self.assertIsNone(introspection_lookup("token"))
        failures = [URLError("down"), TimeoutError(), HTTPError("http://auth/", 401, "Bad client", {}, None)]
        for failure in failures:
            with self.subTest(failure=failure), patch("catalog.auth_client._opener.open", side_effect=failure), self.assertRaises(AuthUnavailable):
                introspection_lookup("token")
        for body in (b"not json", b'{}', b'{"active":"true"}', b"x" * 65537):
            with self.subTest(body=body[:50]), patch("catalog.auth_client._opener.open", return_value=Response(body)), self.assertRaises(AuthUnavailable):
                introspection_lookup("token")
