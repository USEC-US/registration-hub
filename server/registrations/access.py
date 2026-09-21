"""Opaque saved-entry credentials. Raw credentials never enter persistent storage."""

import hashlib
import json
import re

from django.core.exceptions import ValidationError
from django.db import connection
from django.http import Http404
from rest_framework.exceptions import APIException

from .models import RegistrationAccess


class SubmissionConflict(APIException):
    status_code = 409
    default_detail = "This saved submission belongs to a different request."
    default_code = "submission_conflict"


def hash_credential(raw: str) -> str:
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise ValidationError(
            {"registration_access": "Invalid saved registration credential."}
        )
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def submission_digest(payload: dict) -> str:
    normalized = dict(payload)
    for key in ("turnstile_token", "access_credential", "registration_access"):
        normalized.pop(key, None)
    for key in (
        "team_tag",
        "manager_name_snapshot",
        "contact_email_snapshot",
        "contact_discord_snapshot",
    ):
        normalized.setdefault(key, "")
    normalized.setdefault("payment_intent_token", None)
    normalized["members"] = [
        dict(
            member,
            roster_role=member.get("roster_role", "main"),
            student_id_snapshot=member.get("student_id_snapshot", ""),
        )
        for member in normalized.get("members", [])
    ]
    return hashlib.sha256(
        json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def resolve_registration_access(
    raw: str, *, registration_id: int | None = None
) -> RegistrationAccess:
    queryset = RegistrationAccess.objects.select_related("registration")
    if registration_id is not None:
        queryset = queryset.filter(registration_id=registration_id)
    try:
        return queryset.get(credential_hash=hash_credential(raw))
    except RegistrationAccess.DoesNotExist as error:
        raise Http404("Saved registration not found.") from error


def replay_registration(
    *, credential_hash, request_digest, submitted_by, tournament_game_id
):
    access = (
        RegistrationAccess.objects.select_related("registration")
        .filter(credential_hash=credential_hash)
        .first()
    )
    if access is None:
        return None
    registration = access.registration
    try:
        division_id = int(tournament_game_id)
    except (TypeError, ValueError, OverflowError) as error:
        raise SubmissionConflict() from error
    actor_id = submitted_by.pk if submitted_by is not None else None
    if (
        access.request_digest != request_digest
        or registration.submitted_by_id != actor_id
        or registration.tournament_game_id != division_id
    ):
        raise SubmissionConflict()
    registration._submission_replayed = True
    return registration


def lock_submission_credential(credential_hash):
    """Serialize a key before domain row locks, including requests across divisions.

    A transaction-scoped advisory mutex is not a domain row lock. All following
    row locks retain division -> registration -> payment/access order. The unique
    index remains the durable constraint. PostgreSQL releases this on rollback.
    """
    key = int(credential_hash[:16], 16)
    if key >= 2**63:
        key -= 2**64
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])
