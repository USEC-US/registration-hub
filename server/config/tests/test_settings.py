from django.test import SimpleTestCase

from config.env import env_bool, env_list, local_secret_key


class EnvHelperTests(SimpleTestCase):
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
        import os

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
