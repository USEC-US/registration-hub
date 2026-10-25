"""Refresh the local CASSO/VietQR.io catalogue without touching payment destinations."""

import json
from http.client import HTTPException
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Bank

BANKS_URL = "https://api.vietqr.io/v2/banks"
MAX_RESPONSE_BYTES = 1024 * 1024


class BankCatalogueError(ValueError):
    pass


def fetch_bank_catalogue():
    request = Request(BANKS_URL, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (URLError, OSError, HTTPException) as error:
        raise BankCatalogueError(
            "Bank catalogue could not be fetched. Try again later."
        ) from error
    if len(payload) > MAX_RESPONSE_BYTES:
        raise BankCatalogueError("Bank catalogue response exceeds the size limit.")
    return payload


def parse_bank_catalogue(payload):
    try:
        document = json.loads(payload)
    except (ValueError, UnicodeError) as error:
        raise BankCatalogueError("Bank catalogue is not valid JSON.") from error
    if not isinstance(document, dict) or document.get("code") != "00":
        raise BankCatalogueError("Bank catalogue API did not report success.")
    rows = document.get("data")
    if not isinstance(rows, list) or not rows:
        raise BankCatalogueError("Bank catalogue must contain a non-empty bank list.")

    banks = []
    seen = set()
    synced_at = timezone.now()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise BankCatalogueError(f"Bank row {index} is not an object.")
        values = {}
        for source, target in (
            ("bin", "bin"),
            ("name", "name"),
            ("shortName", "short_name"),
            ("code", "code"),
            ("logo", "logo_url"),
            ("swift_code", "swift_code"),
        ):
            value = row.get(source)
            if source in ("logo", "swift_code") and value is None:
                value = ""
            if not isinstance(value, str):
                raise BankCatalogueError(f"Bank row {index}: {source} must be text.")
            values[target] = value.strip()
        for source, target in (
            ("transferSupported", "transfer_supported"),
            ("lookupSupported", "lookup_supported"),
        ):
            value = row.get(source)
            if type(value) is not int or value not in (0, 1):
                raise BankCatalogueError(f"Bank row {index}: {source} must be 0 or 1.")
            values[target] = bool(value)
        bank = Bank(**values, is_active=True, last_synced_at=synced_at)
        try:
            bank.full_clean(validate_unique=False, validate_constraints=False)
        except ValidationError as error:
            raise BankCatalogueError(f"Bank row {index} is invalid: {error}") from error
        if bank.bin in seen:
            raise BankCatalogueError(f"Duplicate bank BIN: {bank.bin}.")
        seen.add(bank.bin)
        banks.append(bank)
    return banks


def sync_bank_catalogue(payload=None, *, dry_run=False, actor=None):
    # Validate the entire response before writing any row or marking banks inactive.
    banks = parse_bank_catalogue(fetch_bank_catalogue() if payload is None else payload)
    bins = {bank.bin for bank in banks}
    with transaction.atomic():
        previous = {
            bank.bin: (bank.short_name, bank.is_active) for bank in Bank.objects.all()
        }
        existing = set(previous)
        result = {
            "created": len(bins - existing),
            "updated": len(bins & existing),
            "deactivated": Bank.objects.filter(is_active=True)
            .exclude(bin__in=bins)
            .count(),
        }
        if not dry_run:
            for bank in banks:
                Bank.objects.update_or_create(
                    bin=bank.bin,
                    defaults={
                        field.name: getattr(bank, field.name)
                        for field in Bank._meta.fields
                        if field.name not in ("id", "bin")
                    },
                )
            Bank.objects.filter(is_active=True).exclude(bin__in=bins).update(
                is_active=False
            )
            if actor is not None:
                for bank in Bank.objects.all():
                    before = previous.get(bank.bin)
                    if bank.bin not in bins and (before is None or not before[1]):
                        continue
                    old = (
                        f"{'active' if before[1] else 'inactive'} ({before[0]})"
                        if before
                        else "absent"
                    )
                    new = f"{'active' if bank.is_active else 'inactive'} ({bank.short_name})"
                    LogEntry.objects.log_actions(
                        user_id=actor.pk,
                        queryset=[bank],
                        action_flag=CHANGE,
                        change_message=f"Bank catalogue refresh: {old} -> {new}",
                    )
    return result
