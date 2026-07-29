from django.test import TestCase, override_settings
from unittest.mock import patch

from config.turnstile import verify_turnstile_token


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


class TurnstileVerificationTests(TestCase):
    @override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
    def test_debug_without_secret_bypasses_verification(self):
        result = verify_turnstile_token(
            "",
            expected_action="sign-in",
            remote_ip="127.0.0.1",
        )

        self.assertTrue(result.success)
        self.assertTrue(result.bypassed)
        self.assertEqual(result.error_codes, ("missing-secret-debug-bypass",))

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_production_without_secret_rejects(self):
        result = verify_turnstile_token(
            "token",
            expected_action="sign-in",
            remote_ip="203.0.113.10",
        )

        self.assertFalse(result.success)
        self.assertFalse(result.bypassed)
        self.assertEqual(result.error_codes, ("missing-secret",))

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="secret")
    def test_siteverify_success_accepts_matching_action(self):
        with patch("config.turnstile.urllib.request.urlopen") as urlopen:
            urlopen.return_value = _Response(
                b'{"success": true, "action": "sign-in"}'
            )

            result = verify_turnstile_token("token", expected_action="sign-in")

        self.assertTrue(result.success)
        self.assertFalse(result.bypassed)

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="secret")
    def test_siteverify_timeout_or_duplicate_rejects_with_retry_code(self):
        with patch("config.turnstile.urllib.request.urlopen") as urlopen:
            urlopen.return_value = _Response(
                b'{"success": false, "error-codes": ["timeout-or-duplicate"]}'
            )

            result = verify_turnstile_token("token", expected_action="sign-in")

        self.assertFalse(result.success)
        self.assertEqual(result.error_codes, ("timeout-or-duplicate",))

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="secret")
    def test_siteverify_action_mismatch_rejects(self):
        with patch("config.turnstile.urllib.request.urlopen") as urlopen:
            urlopen.return_value = _Response(
                b'{"success": true, "action": "account-register"}'
            )

            result = verify_turnstile_token("token", expected_action="sign-in")

        self.assertFalse(result.success)
        self.assertEqual(result.error_codes, ("action-mismatch",))
