from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from tournaments.models import TournamentGame


class Registration(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    tournament_game = models.ForeignKey(
        TournamentGame, on_delete=models.PROTECT, related_name="registrations"
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_registrations",
    )
    team_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    fee_amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    fee_currency_snapshot = models.CharField(max_length=3)
    submitted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def active_statuses(cls) -> tuple[str, ...]:
        return (cls.Status.SUBMITTED, cls.Status.UNDER_REVIEW, cls.Status.APPROVED)


class RegistrationMember(models.Model):
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_registration_memberships",
    )
    gamer_tag_snapshot = models.CharField(max_length=64)
    school_snapshot = models.CharField(max_length=128)
    is_captain = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("display_order", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("registration",),
                condition=Q(is_captain=True),
                name="one_captain_per_registration",
            ),
            models.UniqueConstraint(
                fields=("registration", "display_order"),
                name="unique_member_display_order",
            ),
        ]


class PaymentAttempt(models.Model):
    class Method(models.TextChoices):
        MANUAL_PROOF = "MANUAL_PROOF", "Manual proof"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="payment_attempts"
    )
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    proof_file = models.FileField(upload_to="payment-proofs/%Y/%m/", blank=True)
    reference = models.CharField(max_length=128, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_payment_attempts",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RegistrationStatusEvent(models.Model):
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="status_events"
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, choices=Registration.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registration_status_events",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
