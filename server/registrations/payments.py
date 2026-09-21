"""Internal tracking references and separate, snapshotted transfer instructions."""

import secrets

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from tournaments.models import TournamentGame
from tournaments.payment_content import (
    snapshot_transfer_template,
    render_transfer_content,
)
from .models import PaymentIntent, Registration
from .reservations import (
    active_registrations,
    lock_registration,
    is_expired,
    expire_due_registrations,
)

PAYMENT_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class LegacyPaymentSessionError(ValidationError):
    """An old quote cannot be silently replaced after a possible bank transfer."""


@transaction.atomic
def create_payment_intent(*, tournament_game, registration=None, payment_settings=None):
    if registration is not None:
        registration = lock_registration(registration.pk)
        if registration.tournament_game_id != tournament_game.pk:
            raise ValidationError("Payment division does not match registration.")
        if is_expired(registration, now=timezone.now()) or (
            registration.payment_due_at is not None
            and registration.status == Registration.Status.REJECTED
        ):
            raise ValidationError("This payment reservation is no longer active.")
    tournament_game = (
        TournamentGame.objects.select_for_update()
        .select_related("tournament")
        .get(pk=tournament_game.pk)
    )
    amount = (
        registration.fee_amount_snapshot if registration else tournament_game.fee_amount
    )
    currency = (
        registration.fee_currency_snapshot
        if registration
        else tournament_game.fee_currency
    )
    if amount <= 0:
        raise ValidationError(
            {"payment_reference": "This registration has no payment due."}
        )
    template = snapshot_transfer_template(
        tournament_game.tournament.transfer_content_template,
        tournament_game.tournament.name,
    )
    limit = tournament_game.tournament.transfer_content_limit
    content = ""
    if registration:
        member = registration.members.order_by("display_order").first()
        participant = (
            registration.team_tag
            or registration.team_name
            or (member.gamer_tag_snapshot if member else "")
        )
        if participant or "{participant}" not in template:
            content = render_transfer_content(template, participant, limit)
    destination_snapshot = {}
    if payment_settings is not None:
        destination_snapshot = {
            "bank_name_snapshot": payment_settings.bank_name,
            "bank_bin_snapshot": payment_settings.bank_bin,
            "account_number_snapshot": payment_settings.account_number,
            "account_holder_snapshot": payment_settings.account_holder,
        }
    for _ in range(5):
        reference = "USEC" + "".join(
            secrets.choice(PAYMENT_ALPHABET) for _ in range(10)
        )
        try:
            with transaction.atomic():
                return PaymentIntent.objects.create(
                    reference=reference,
                    transfer_content_template=template,
                    transfer_content_limit=limit,
                    transfer_content=content,
                    tournament_game=tournament_game,
                    registration=registration,
                    amount=amount,
                    currency=currency,
                    **destination_snapshot,
                )
        except IntegrityError:
            if not PaymentIntent.objects.filter(reference=reference).exists():
                raise
    raise ValidationError(
        {"payment_reference": "Could not generate a payment reference. Try again."}
    )


@transaction.atomic
def reserve_payment_reference(*, tournament_game_id, token=None):
    game = (
        TournamentGame.objects.select_for_update()
        .select_related("tournament")
        .get(pk=tournament_game_id)
    )
    if token:
        # Resume the same quote even if the registration window has since closed.
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(token=token, tournament_game=game, registration__isnull=True)
            .first()
        )
        if not intent:
            raise ValidationError(
                {
                    "payment_reference": "This payment reference is unavailable. Contact the organizers if you have already paid."
                }
            )
        if not intent.transfer_content_template:
            raise LegacyPaymentSessionError(
                {
                    "transfer_content": "These older payment instructions cannot be resumed. Contact the organizers if you have already paid."
                }
            )
        return intent
    if (
        not game.tournament.is_published
        or not game.registration_opens_at
        <= timezone.now()
        < game.registration_closes_at
    ):
        raise ValidationError({"payment_reference": "Registration is not open."})
    expire_due_registrations(division_id=game.pk)
    if (
        game.registration_capacity is not None
        and active_registrations(now=timezone.now())
        .filter(tournament_game=game)
        .count()
        >= game.registration_capacity
    ):
        raise ValidationError(
            {"payment_reference": "Registration capacity has been reached."}
        )
    return create_payment_intent(tournament_game=game)
