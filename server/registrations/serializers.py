from django.utils import timezone
from rest_framework import serializers

from tournaments.models import TournamentGame

from .models import (
    PaymentAttempt,
    Registration,
    RegistrationMember,
    RegistrationStatusEvent,
)
from .services import RegistrationMemberInput


class TournamentGameSummarySerializer(serializers.ModelSerializer):
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    game_name = serializers.CharField(source="game.name", read_only=True)

    class Meta:
        model = TournamentGame
        fields = (
            "id",
            "tournament_name",
            "game_name",
            "main_roster_size",
            "substitute_limit",
            "fee_amount",
            "fee_currency",
        )


class RegistrationMemberReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationMember
        fields = (
            "gamer_tag_snapshot",
            "school_snapshot",
            "is_captain",
            "roster_role",
            "display_order",
        )


class RegistrationStatusEventReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationStatusEvent
        fields = ("to_status", "created_at")


class PaymentAttemptReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAttempt
        fields = ("id", "status", "amount", "currency", "created_at")


class RegistrationReadSerializer(serializers.ModelSerializer):
    tournament_game = TournamentGameSummarySerializer(read_only=True)
    members = RegistrationMemberReadSerializer(many=True, read_only=True)
    status_events = RegistrationStatusEventReadSerializer(many=True, read_only=True)
    payment_attempts = PaymentAttemptReadSerializer(many=True, read_only=True)
    payment_required = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = (
            "id",
            "tournament_game",
            "team_name",
            "status",
            "fee_amount_snapshot",
            "fee_currency_snapshot",
            "payment_required",
            "submitted_at",
            "members",
            "status_events",
            "payment_attempts",
        )

    def get_payment_required(self, obj: Registration) -> bool:
        return obj.fee_amount_snapshot > 0


class StrictFieldsSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            return super().to_internal_value(data)
        unknown_fields = set(data.keys()) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError(
                {
                    field: "This field is not allowed."
                    for field in sorted(unknown_fields)
                }
            )
        return super().to_internal_value(data)


class RegistrationMemberSubmissionSerializer(StrictFieldsSerializer):
    first_name_snapshot = serializers.CharField(max_length=150)
    last_name_snapshot = serializers.CharField(max_length=150)
    date_of_birth_snapshot = serializers.DateField()
    student_id_snapshot = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default=""
    )
    gamer_tag_snapshot = serializers.CharField(max_length=64)
    institution_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True
    )
    institution_label = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )

    def validate(self, attrs):
        if bool(attrs.get("institution_id")) == bool(attrs.get("institution_label")):
            raise serializers.ValidationError(
                "Choose a catalogue institution or enter a custom label."
            )
        return attrs

    def validate_date_of_birth_snapshot(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    is_captain = serializers.BooleanField()
    roster_role = serializers.ChoiceField(
        choices=RegistrationMember.RosterRole.choices, default="main"
    )
    display_order = serializers.IntegerField(min_value=1)


class RegistrationSubmissionSerializer(StrictFieldsSerializer):
    submitter_role = serializers.ChoiceField(choices=Registration.SubmitterRole.choices)
    manager_name_snapshot = serializers.CharField(
        max_length=100, allow_blank=True, required=False
    )
    contact_facebook_snapshot = serializers.CharField(max_length=255)
    contact_phone_snapshot = serializers.CharField(max_length=32)
    contact_email_snapshot = serializers.EmailField(allow_blank=True, required=False)
    contact_discord_snapshot = serializers.CharField(
        max_length=100, allow_blank=True, required=False
    )

    tournament_game = serializers.PrimaryKeyRelatedField(
        queryset=TournamentGame.objects.all()
    )
    team_name = serializers.CharField(max_length=100, allow_blank=True)
    members = RegistrationMemberSubmissionSerializer(many=True)
    turnstile_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    def to_member_inputs(self) -> list[RegistrationMemberInput]:
        return [
            RegistrationMemberInput(**member)
            for member in self.validated_data["members"]
        ]


class PaymentAttemptSubmissionSerializer(StrictFieldsSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    proof_file = serializers.FileField()
    reference = serializers.CharField(max_length=128, allow_blank=True, required=False)
    turnstile_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )


class PaymentAttemptReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAttempt
        fields = ("id", "status", "amount", "currency", "created_at")
