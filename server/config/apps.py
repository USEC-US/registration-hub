from django.apps import AppConfig


class ConfigConfig(AppConfig):
    name = "config"

    def ready(self):
        import config.checks  # noqa: F401
