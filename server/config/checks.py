from django.conf import settings
from django.core.checks import Error, register


@register()
def check_turnstile_settings(app_configs, **kwargs):
    if settings.DEBUG or settings.TURNSTILE_SECRET_KEY:
        return []
    return [
        Error(
            "TURNSTILE_SECRET_KEY must be set when DEBUG=False.",
            id="config.E001",
        )
    ]
