import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from tournaments.models import TournamentGame


class Registration(models.Model):
    class SubmitterRole(models.TextChoices):
        CAPTAIN = "captain", "Captain"
        MANAGER = "manager", "Manager"

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
        null=True,
        blank=True,
    )
    submitter_role = models.CharField(
        max_length=10, choices=SubmitterRole.choices, blank=True
    )
    manager_name_snapshot = models.CharField(max_length=100, blank=True)
    contact_facebook_snapshot = models.CharField(max_length=255, blank=True)
    contact_phone_snapshot = models.CharField(max_length=32, blank=True)
    contact_email_snapshot = models.EmailField(blank=True)
    contact_discord_snapshot = models.CharField(max_length=100, blank=True)
    team_name = models.CharField(max_length=100, blank=True)
    team_tag = models.CharField(max_length=5, blank=True)
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
    class RosterRole(models.TextChoices):
        MAIN = "main", "Main player"
        SUBSTITUTE = "substitute", "Substitute"

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
    first_name_snapshot = models.CharField("first name", max_length=150, blank=True)
    last_name_snapshot = models.CharField("last name", max_length=150, blank=True)
    date_of_birth_snapshot = models.DateField("date of birth", null=True, blank=True)
    student_id_snapshot = models.CharField("student ID", max_length=128, blank=True)
    institution = models.ForeignKey(
        "accounts.Institution",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registration_members",
    )
    school_snapshot = models.CharField(max_length=255)
    is_captain = models.BooleanField(default=False)
    roster_role = models.CharField(
        max_length=10, choices=RosterRole.choices, default=RosterRole.MAIN
    )
    display_order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("display_order", "pk")
        constraints = [
            models.CheckConstraint(
                condition=Q(roster_role__in=("main", "substitute")),
                name="registration_member_valid_roster_role",
            ),
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


class PaymentIntent(models.Model):
    transfer_content_template = models.TextField(blank=True, editable=False)
    transfer_content_limit = models.PositiveSmallIntegerField(
        default=100, editable=False
    )
    transfer_content = models.CharField(max_length=150, blank=True, editable=False)
    # Private claim token; the payment reference itself never grants access.
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reference = models.CharField(max_length=14, unique=True, editable=False)
    tournament_game = models.ForeignKey(
        "tournaments.TournamentGame", on_delete=models.PROTECT
    )
    registration = models.OneToOneField(
        Registration,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_intent",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)
