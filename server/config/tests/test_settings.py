import importlib
import os

from django.core.checks import Error
from django.test import SimpleTestCase
from django.test import override_settings

from config.checks import check_turnstile_settings
from config.env import env_bool, env_list, local_secret_key


class EnvHelperTests(SimpleTestCase):
    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_turnstile_secret_is_required_outside_debug(self):
        messages = check_turnstile_settings(app_configs=None)

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, "config.E001")

    @override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
    def test_turnstile_secret_can_be_missing_in_debug(self):
        self.assertEqual(check_turnstile_settings(app_configs=None), [])

    def test_env_list_discards_empty_values(self):
        with self.settings():
            import os

            previous = os.environ.get("EXAMPLE_LIST")
            os.environ["EXAMPLE_LIST"] = "localhost,, 127.0.0.1 ,"
            try:
                self.assertEqual(env_list("EXAMPLE_LIST"), ["localhost", "127.0.0.1"])
            finally:
                if previous is None:
                    os.environ.pop("EXAMPLE_LIST", None)
                else:
                    os.environ["EXAMPLE_LIST"] = previous

    def test_env_bool_accepts_common_true_values(self):
        import os

        previous = os.environ.get("EXAMPLE_BOOL")
        os.environ["EXAMPLE_BOOL"] = "true"
        try:
            self.assertTrue(env_bool("EXAMPLE_BOOL"))
        finally:
            if previous is None:
                os.environ.pop("EXAMPLE_BOOL", None)
            else:
                os.environ["EXAMPLE_BOOL"] = previous

    def test_secret_key_uses_local_fallback_only_in_debug(self):
        previous = os.environ.get("EMPTY_SECRET_KEY")
        os.environ.pop("EMPTY_SECRET_KEY", None)
        try:
            self.assertEqual(
                local_secret_key("EMPTY_SECRET_KEY", debug=True),
                "local-development-secret-key",
            )
            with self.assertRaises(RuntimeError):
                local_secret_key("EMPTY_SECRET_KEY", debug=False)
        finally:
            if previous is not None:
                os.environ["EMPTY_SECRET_KEY"] = previous

    def test_csrf_trusted_origins_include_cors_origins_by_default(self):
        import config.settings as settings_module

        previous_cors = os.environ.get("CORS_ALLOWED_ORIGINS")
        previous_csrf = os.environ.get("CSRF_ALLOWED_ORIGINS")
        previous_cors_origins = os.environ.get("CORS_ORIGINS")

        os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        os.environ.pop("CSRF_ALLOWED_ORIGINS", None)
        os.environ["CORS_ORIGINS"] = "http://example.test,http://localhost:5173"

        try:
            settings_module = importlib.reload(settings_module)
            self.assertIn("http://localhost:5173", settings_module.CSRF_TRUSTED_ORIGINS)
            self.assertIn("http://example.test", settings_module.CSRF_TRUSTED_ORIGINS)
        finally:
            if previous_cors is None:
                os.environ.pop("CORS_ALLOWED_ORIGINS", None)
            else:
                os.environ["CORS_ALLOWED_ORIGINS"] = previous_cors

            if previous_csrf is None:
                os.environ.pop("CSRF_ALLOWED_ORIGINS", None)
            else:
                os.environ["CSRF_ALLOWED_ORIGINS"] = previous_csrf

            if previous_cors_origins is None:
                os.environ.pop("CORS_ORIGINS", None)
            else:
                os.environ["CORS_ORIGINS"] = previous_cors_origins

            importlib.reload(settings_module)
