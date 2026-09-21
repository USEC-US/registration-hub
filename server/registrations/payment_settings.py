"""Validation and lookup for the site-wide receiving-bank settings."""

from decimal import Decimal
import re

from django.core.exceptions import ValidationError

from .models import PaymentSettings
from .vietqr import build_vietqr


_ASCII_BIN = re.compile(r"[0-9]{6}\Z", re.ASCII)
_ASCII_ACCOUNT = re.compile(r"[0-9A-Za-z]{1,19}\Z", re.ASCII)


def payment_destination_errors(
    *, bank_name: str, bank_bin: str, account_number: str, account_holder: str
) -> dict[str, str]:
    errors = {}
    if not bank_name.strip():
        errors["bank_name"] = "Bank display name is required when payments are enabled."
    if not _ASCII_BIN.fullmatch(bank_bin):
        errors["bank_bin"] = "Bank BIN must contain exactly six ASCII digits."
    if not _ASCII_ACCOUNT.fullmatch(account_number):
        errors["account_number"] = (
            "Account number must contain 1 to 19 ASCII letters or digits."
        )
    if not account_holder.strip():
        errors["account_holder"] = (
            "Account-holder name is required when payments are enabled."
        )
    return errors


def require_payment_settings(*, amount: Decimal, currency: str) -> PaymentSettings:
    """Return usable receiving settings or reject a new paid registration."""
    try:
        settings = PaymentSettings.objects.get(pk=1)
    except PaymentSettings.DoesNotExist as error:
        raise ValidationError(
            {"payment_settings": "Receiving-bank settings are not configured."}
        ) from error
    if not settings.enabled:
        raise ValidationError(
            {"payment_settings": "Receiving-bank settings are disabled."}
        )
    if currency != "VND":
        raise ValidationError(
            {"currency": "New VietQR payment registrations require VND."}
        )
    settings.full_clean()
    # Reuse the strict encoder boundary so settings and issued QR amounts cannot drift.
    build_vietqr(
        bank_bin=settings.bank_bin,
        account_number=settings.account_number,
        amount=amount,
        transfer_content="",
    )
    return settings
