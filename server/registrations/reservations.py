"""Effective reservations; all mutations serialize on the owning division first."""

from datetime import datetime

from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone
from tournaments.models import TournamentGame
from .models import PaymentAttempt, Registration, RegistrationStatusEvent


def active_registrations(*, now: datetime) -> QuerySet[Registration]:
    protected = PaymentAttempt.objects.filter(
        registration_id=OuterRef("pk"), status__in=("PENDING", "VERIFIED")
    )
    return (
        Registration.objects.alias(protected_payment=Exists(protected))
        .filter(status__in=Registration.active_statuses())
        .exclude(
            fee_amount_snapshot__gt=0, payment_due_at__lte=now, protected_payment=False
        )
    )


def payment_state(registration: Registration) -> str:
    if registration.fee_amount_snapshot <= 0:
        return "NOT_REQUIRED"
    statuses = set(registration.payment_attempts.values_list("status", flat=True))
    return next(
        (
            status
            for status in ("VERIFIED", "PENDING", "REJECTED")
            if status in statuses
        ),
        "UNPAID",
    )


def is_expired(registration: Registration, *, now: datetime) -> bool:
    return registration.status == Registration.Status.EXPIRED or (
        registration.status in Registration.active_statuses()
        and registration.fee_amount_snapshot > 0
        and registration.payment_due_at is not None
        and registration.payment_due_at <= now
        and payment_state(registration) not in ("PENDING", "VERIFIED")
    )


def lock_registration(registration_id):
    """Caller must hold an atomic transaction. Never lock a nullable joined owner."""
    division_id = Registration.objects.values_list("tournament_game_id", flat=True).get(
        pk=registration_id
    )
    TournamentGame.objects.select_for_update().get(pk=division_id)
    return Registration.objects.select_for_update().get(pk=registration_id)


def expire_due_registrations(*, division_id: int | None = None) -> int:
    divisions = TournamentGame.objects.all()
    if division_id is not None:
        divisions = divisions.filter(pk=division_id)
    count = 0
    for pk in divisions.order_by("pk").values_list("pk", flat=True):
        with transaction.atomic():
            TournamentGame.objects.select_for_update().get(pk=pk)
            candidates = (
                Registration.objects.select_for_update()
                .filter(
                    tournament_game_id=pk,
                    status__in=Registration.active_statuses(),
                    fee_amount_snapshot__gt=0,
                    payment_due_at__lte=timezone.now(),
                )
                .order_by("pk")
            )
            for registration in candidates:
                if is_expired(registration, now=timezone.now()):
                    previous = registration.status
                    registration.status = Registration.Status.EXPIRED
                    registration.save(update_fields=("status", "updated_at"))
                    RegistrationStatusEvent.objects.create(
                        registration=registration,
                        from_status=previous,
                        to_status=Registration.Status.EXPIRED,
                        note="Payment reservation expired.",
                    )
                    count += 1
    return count
