from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from rest_framework.exceptions import ValidationError as DRFValidationError


logger = logging.getLogger(__name__)
_debug_bypass_warning_emitted = False


@dataclass(frozen=True)
class TurnstileVerificationResult:
    success: bool
    bypassed: bool = False
    error_codes: tuple[str, ...] = ()


def verify_turnstile_token(
    token: str,
    *,
    expected_action: str,
    remote_ip: str | None = None,
) -> TurnstileVerificationResult:
    global _debug_bypass_warning_emitted

    secret = settings.TURNSTILE_SECRET_KEY
    if not secret:
        if settings.DEBUG:
            if not _debug_bypass_warning_emitted:
                logger.warning(
                    "Turnstile secret is missing; using the DEBUG-only local "
                    "development bypass."
                )
                _debug_bypass_warning_emitted = True
            return TurnstileVerificationResult(
                success=True,
                bypassed=True,
                error_codes=("missing-secret-debug-bypass",),
            )
        return TurnstileVerificationResult(success=False, error_codes=("missing-secret",))

    if not token:
        return TurnstileVerificationResult(
            success=False,
            error_codes=("missing-input-response",),
        )

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    request = urllib.request.Request(
        settings.TURNSTILE_SITEVERIFY_URL,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return TurnstileVerificationResult(
            success=False,
            error_codes=("siteverify-unavailable",),
        )

    error_codes = tuple(data.get("error-codes", ()))
    if not data.get("success"):
        return TurnstileVerificationResult(success=False, error_codes=error_codes)

    if data.get("action") != expected_action:
        return TurnstileVerificationResult(
            success=False,
            error_codes=("action-mismatch",),
        )

    return TurnstileVerificationResult(success=True)


def require_turnstile(request, *, token: str, expected_action: str) -> None:
    result = verify_turnstile_token(
        token,
        expected_action=expected_action,
        remote_ip=request.META.get("REMOTE_ADDR"),
    )
    if not result.success:
        raise DRFValidationError(
            {"turnstile_token": list(result.error_codes) or ["invalid"]}
        )
