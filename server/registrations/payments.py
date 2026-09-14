"""Provider-independent payment codes for manual transfers and future webhooks."""

import secrets

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from tournaments.models import TournamentGame
from .models import PaymentIntent, Registration

PAYMENT_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def create_payment_intent(*, tournament_game, registration=None):
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
    for _ in range(5):
        reference = "USEC" + "".join(
            secrets.choice(PAYMENT_ALPHABET) for _ in range(10)
        )
        try:
            with transaction.atomic():
                return PaymentIntent.objects.create(
                    reference=reference,
                    tournament_game=tournament_game,
                    registration=registration,
                    amount=amount,
                    currency=currency,
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
        intent = PaymentIntent.objects.filter(
            token=token, tournament_game=game, registration__isnull=True
        ).first()
        if not intent:
            raise ValidationError(
                {
                    "payment_reference": "This payment reference is unavailable. Contact the organizers if you have already paid."
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
    if (
        game.registration_capacity is not None
        and Registration.objects.filter(
            tournament_game=game, status__in=Registration.active_statuses()
        ).count()
        >= game.registration_capacity
    ):
        raise ValidationError(
            {"payment_reference": "Registration capacity has been reached."}
        )
    return create_payment_intent(tournament_game=game)
