from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from tournaments.models import TournamentGame

from .models import (
    PaymentAttempt,
    Registration,
    RegistrationMember,
    RegistrationStatusEvent,
)


@dataclass(frozen=True)
class RegistrationMemberInput:
    gamer_tag_snapshot: str
    school_snapshot: str
    is_captain: bool
    display_order: int


def submit_registration(
    *,
    submitted_by,
    tournament_game_id: int,
    team_name: str,
    members: Sequence[RegistrationMemberInput],
) -> Registration:
    with transaction.atomic():
        tournament_game = TournamentGame.objects.select_for_update().get(
            pk=tournament_game_id
        )
        now = timezone.now()
        if not tournament_game.registration_opens_at <= now < tournament_game.registration_closes_at:
            raise ValidationError("Registration is not open.")

        active = Registration.objects.filter(
            tournament_game=tournament_game,
            status__in=Registration.active_statuses(),
        )
        if (
            tournament_game.registration_capacity is not None
            and active.count() >= tournament_game.registration_capacity
        ):
            raise ValidationError("Registration capacity has been reached.")

        _validate_roster(
            tournament_game=tournament_game,
            team_name=team_name,
            members=members,
        )

        registration = Registration.objects.create(
            tournament_game=tournament_game,
            submitted_by=submitted_by,
            team_name=team_name.strip(),
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=tournament_game.fee_amount,
            fee_currency_snapshot=tournament_game.fee_currency,
        )
        RegistrationMember.objects.bulk_create(
            [
                RegistrationMember(
                    registration=registration,
                    gamer_tag_snapshot=member.gamer_tag_snapshot.strip(),
                    school_snapshot=member.school_snapshot.strip(),
                    is_captain=member.is_captain,
                    display_order=member.display_order,
                )
                for member in members
            ]
        )
        RegistrationStatusEvent.objects.create(
            registration=registration,
            from_status="",
            to_status=Registration.Status.SUBMITTED,
            actor=submitted_by,
        )
        return registration


def _validate_roster(
    *,
    tournament_game: TournamentGame,
    team_name: str,
    members: Sequence[RegistrationMemberInput],
) -> None:
    if not tournament_game.team_size_min <= len(members) <= tournament_game.team_size_max:
        raise ValidationError("Roster size is outside the configured limit.")
    if sum(member.is_captain for member in members) != 1:
        raise ValidationError("A registration must have exactly one captain.")
    if bool(team_name.strip()) != tournament_game.is_team:
        raise ValidationError("A team name is required exactly for team games.")
    if any(member.display_order < 1 for member in members):
        raise ValidationError("Roster display order must start at one.")
    if len({member.display_order for member in members}) != len(members):
        raise ValidationError("Roster display order must be unique.")
    if {member.display_order for member in members} != set(range(1, len(members) + 1)):
        raise ValidationError("Roster display order must be contiguous from one.")
    if any(
        not member.gamer_tag_snapshot.strip() or not member.school_snapshot.strip()
        for member in members
    ):
        raise ValidationError("Every player needs a gamer tag and school snapshot.")


def _require_organizer(actor, permission: str) -> None:
    if actor.is_authenticated and actor.is_superuser:
        return
    if (
        actor.is_authenticated
        and actor.is_staff
        and actor.groups.filter(name="Organizers").exists()
        and actor.has_perm(permission)
    ):
        return
    raise PermissionDenied("An Organizer staff account is required.")


def _transition_registration(
    *,
    actor,
    registration_id: int,
    expected_status: str,
    to_status: str,
    note: str = "",
) -> Registration:
    _require_organizer(actor, "registrations.change_registration")
    with transaction.atomic():
        registration = Registration.objects.select_for_update().get(pk=registration_id)
        if registration.status != expected_status:
            raise ValidationError(
                f"Cannot move a {registration.status} registration to {to_status}."
            )
        registration.status = to_status
        registration.save(update_fields=("status", "updated_at"))
        RegistrationStatusEvent.objects.create(
            registration=registration,
            from_status=expected_status,
            to_status=to_status,
            actor=actor,
            note=note.strip(),
        )
        return registration


def start_review(*, actor, registration_id: int, note: str = "") -> Registration:
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.SUBMITTED,
        to_status=Registration.Status.UNDER_REVIEW,
        note=note,
    )


def approve_registration(*, actor, registration_id: int, note: str = "") -> Registration:
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.UNDER_REVIEW,
        to_status=Registration.Status.APPROVED,
        note=note,
    )


def reject_registration(*, actor, registration_id: int, note: str) -> Registration:
    if not note.strip():
        raise ValidationError("A rejection reason is required.")
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.UNDER_REVIEW,
        to_status=Registration.Status.REJECTED,
        note=note,
    )


def submit_payment_attempt(
    *,
    actor,
    registration_id: int,
    amount: Decimal,
    currency: str,
    proof_file=None,
    reference: str = "",
) -> PaymentAttempt:
    with transaction.atomic():
        registration = Registration.objects.select_for_update().get(pk=registration_id)
        if registration.submitted_by_id != actor.pk:
            raise PermissionDenied("Only the submitter can add a payment attempt.")
        if registration.fee_amount_snapshot <= Decimal("0.00"):
            raise ValidationError("This registration has no payment due.")
        if amount != registration.fee_amount_snapshot:
            raise ValidationError("Payment amount must match the registration fee.")
        if currency.upper() != registration.fee_currency_snapshot:
            raise ValidationError("Payment currency must match the registration fee.")
        if proof_file is None and not reference.strip():
            raise ValidationError("Provide either a payment proof file or a reference.")

        return PaymentAttempt.objects.create(
            registration=registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            status=PaymentAttempt.Status.PENDING,
            amount=amount,
            currency=currency.upper(),
            proof_file=proof_file,
            reference=reference.strip(),
        )


def review_payment_attempt(
    *,
    actor,
    payment_attempt_id: int,
    status: str,
    note: str = "",
) -> PaymentAttempt:
    _require_organizer(actor, "registrations.change_paymentattempt")
    if status not in {PaymentAttempt.Status.VERIFIED, PaymentAttempt.Status.REJECTED}:
        raise ValidationError("A payment attempt may only be verified or rejected.")

    with transaction.atomic():
        payment_attempt = PaymentAttempt.objects.select_for_update().get(
            pk=payment_attempt_id
        )
        if payment_attempt.status != PaymentAttempt.Status.PENDING:
            raise ValidationError("Only a pending payment attempt may be reviewed.")
        payment_attempt.status = status
        payment_attempt.reviewed_by = actor
        payment_attempt.reviewed_at = timezone.now()
        payment_attempt.review_note = note.strip()
        payment_attempt.save(
            update_fields=("status", "reviewed_by", "reviewed_at", "review_note")
        )
        return payment_attempt
