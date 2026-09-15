"""Private payment state derived from immutable registration and intent snapshots."""

import base64

from django.utils import timezone

from .models import Registration
from .reservations import is_expired, payment_state
from .serializers import RegistrationReadSerializer
from .vietqr import build_vietqr, render_vietqr_png


def build_payment_session(registration: Registration) -> dict:
    now = timezone.now()
    state = payment_state(registration)
    expired = is_expired(registration, now=now)
    active = registration.status in Registration.active_statuses()
    published = registration.tournament_game.tournament.is_published
    can_upload = (
        active and published and not expired and state in ("UNPAID", "REJECTED")
    )
    latest_rejection = (
        registration.payment_attempts.filter(status="REJECTED")
        .order_by("-reviewed_at", "-pk")
        .first()
    )
    saved = {
        field: getattr(registration, field)
        for field in (
            "team_name",
            "team_tag",
            "submitter_role",
            "manager_name_snapshot",
            "contact_facebook_snapshot",
            "contact_phone_snapshot",
            "contact_email_snapshot",
            "contact_discord_snapshot",
        )
    }
    saved["tournament_game"] = registration.tournament_game_id
    saved["members"] = []
    labels = {}
    for member in registration.members.order_by("display_order"):
        item = {
            field: getattr(member, field)
            for field in (
                "gamer_tag_snapshot",
                "first_name_snapshot",
                "last_name_snapshot",
                "student_id_snapshot",
                "is_captain",
                "roster_role",
                "display_order",
            )
        }
        item["date_of_birth_snapshot"] = (
            member.date_of_birth_snapshot.isoformat()
            if member.date_of_birth_snapshot
            else None
        )
        if member.institution_id:
            item["institution_id"] = member.institution_id
        else:
            item["institution_label"] = member.school_snapshot
        labels[str(member.display_order)] = member.school_snapshot
        saved["members"].append(item)
    instructions = None
    try:
        intent = registration.payment_intent
    except Registration.payment_intent.RelatedObjectDoesNotExist:
        intent = None
    if intent and registration.fee_amount_snapshot > 0:
        instructions = {
            "bank_name": intent.bank_name_snapshot,
            "bank_bin": intent.bank_bin_snapshot,
            "account_number": intent.account_number_snapshot,
            "account_holder": intent.account_holder_snapshot,
            "amount": str(intent.amount),
            "currency": intent.currency,
            "transfer_content": intent.transfer_content,
            "transfer_content_limit": intent.transfer_content_limit,
            "qr_payload": None,
            "qr_png_data_url": None,
            "qr_contains_transfer_content": False,
        }
        if (
            can_upload
            and intent.bank_bin_snapshot
            and intent.account_number_snapshot
            and intent.currency == "VND"
        ):
            payload, includes = build_vietqr(
                bank_bin=intent.bank_bin_snapshot,
                account_number=intent.account_number_snapshot,
                amount=intent.amount,
                transfer_content=intent.transfer_content,
            )
            instructions.update(
                qr_payload=payload,
                qr_contains_transfer_content=includes,
                qr_png_data_url="data:image/png;base64,"
                + base64.b64encode(
                    render_vietqr_png(
                        payload=payload, copy_transfer_content=not includes
                    )
                ).decode("ascii"),
            )
    return {
        "tournament_slug": registration.tournament_game.tournament.slug,
        "registration": RegistrationReadSerializer(registration).data,
        "payment_state": state,
        "payment_due_at": registration.payment_due_at.isoformat()
        if registration.payment_due_at
        else None,
        "server_now": now.isoformat(),
        "expired": expired,
        "can_upload_proof": can_upload,
        "can_retry_registration": expired,
        "replacement_note": latest_rejection.review_note
        if state == "REJECTED" and latest_rejection
        else "",
        "saved_submission": saved,
        "institution_labels": labels,
        "instructions": instructions,
    }
