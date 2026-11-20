import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from review_auth import (
    AuthUnavailable, Identity, InvalidToken, PermissionDenied, Role, VerifiedToken,
    encode_introspection, error_payload, parse_introspection, require_editor, verify_token,
)


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
        self.user = Identity(UUID("84240d8e-1db4-4b50-a90f-1d064eb289d2"), "sarah_k", Role.EDITOR)
        self.active = VerifiedToken(self.user, self.now + timedelta(hours=1))

    def test_lookup_is_injected_and_invoked_on_every_check(self):
        calls = []
        def lookup(token):
            calls.append(token)
            return self.active
        self.assertEqual(verify_token("opaque", lookup, now=self.now), self.active)
        verify_token("opaque", lookup, now=self.now)
        self.assertEqual(calls, ["opaque", "opaque"])

    def test_role_change_is_observed_without_replacing_token(self):
        result = self.active
        lookup = lambda token: result
        require_editor(verify_token("same-token", lookup, now=self.now).user)
        result = VerifiedToken(Identity(self.user.id, "sarah_k", Role.READER), self.active.expires_at)
        with self.assertRaises(PermissionDenied):
            require_editor(verify_token("same-token", lookup, now=self.now).user)

    def test_inactive_token(self):
        with self.assertRaises(InvalidToken):
            verify_token("opaque", lambda token: None, now=self.now)

    def test_expiry_boundary_is_exclusive(self):
        for expiry in [self.now, self.now - timedelta(seconds=1)]:
            with self.subTest(expiry=expiry), self.assertRaises(InvalidToken):
                verify_token("opaque", lambda token: VerifiedToken(self.user, expiry), now=self.now)

    def test_missing_token_does_not_call_lookup(self):
        def lookup(_):
            self.fail("An absent credential must not be looked up.")
        for token in ["", " ", None, 42]:
            with self.subTest(token=token), self.assertRaises(InvalidToken):
                verify_token(token, lookup, now=self.now)

    def test_lookup_failure_is_unavailable_not_invalid(self):
        def lookup(_):
            raise OSError("database unavailable")
        with self.assertRaises(AuthUnavailable):
            verify_token("opaque", lookup, now=self.now)

    def test_explicit_lookup_outcomes_are_preserved(self):
        for error in [InvalidToken("revoked"), AuthUnavailable("timeout")]:
            def lookup(_):
                raise error
            with self.subTest(error=error), self.assertRaises(type(error)):
                verify_token("opaque", lookup, now=self.now)

    def test_malformed_lookup_results_fail_closed(self):
        for result in [
            {}, True, "editor",
            VerifiedToken(Identity(self.user.id, "sarah_k", "owner"), self.active.expires_at),
            VerifiedToken(self.user, datetime(2026, 12, 1)),
        ]:
            with self.subTest(result=result), self.assertRaises(AuthUnavailable):
                verify_token("opaque", lambda token: result, now=self.now)

    def test_active_response_round_trips(self):
        payload = encode_introspection(self.active)
        self.assertEqual(payload["user"]["id"], str(self.user.id))
        self.assertEqual(payload["expires_at"], "2026-11-19T13:00:00Z")
        self.assertEqual(parse_introspection(payload), self.active)

    def test_inactive_response_discloses_no_identity(self):
        self.assertEqual(encode_introspection(None), {"active": False})
        self.assertIsNone(parse_introspection({"active": False}))

    def test_unusable_network_response_is_unavailable(self):
        valid = encode_introspection(self.active)
        invalid = [
            None, [], {}, {"active": 1}, {"active": "true"}, {"active": True},
            {**valid, "user": []}, {**valid, "expires_at": "tomorrow"},
            {**valid, "expires_at": "2026-11-19T13:00:00"},
            {**valid, "user": {**valid["user"], "role": "superuser"}},
            {**valid, "user": {**valid["user"], "id": "123"}},
            {**valid, "user": {**valid["user"], "username": " "}},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(AuthUnavailable):
                parse_introspection(payload)

    def test_additive_response_fields_are_compatible(self):
        payload = encode_introspection(self.active)
        payload["new_optional_field"] = "future"
        self.assertEqual(parse_introspection(payload), self.active)

    def test_offset_expiry_normalizes_to_utc(self):
        payload = encode_introspection(self.active)
        payload["expires_at"] = "2026-11-19T08:00:00-05:00"
        self.assertEqual(parse_introspection(payload), self.active)

    def test_error_representation_leaves_http_status_to_service(self):
        self.assertEqual(
            error_payload("invalid_sort", "Unsupported sort.", parameter="sort"),
            {"error": {"code": "invalid_sort", "message": "Unsupported sort.", "parameter": "sort"}},
        )


if __name__ == "__main__":
    unittest.main()
