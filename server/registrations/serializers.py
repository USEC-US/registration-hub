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
            "team_size_min",
            "team_size_max",
            "fee_amount",
            "fee_currency",
        )


class RegistrationMemberReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationMember
        fields = ("gamer_tag_snapshot", "school_snapshot", "is_captain", "display_order")


class RegistrationStatusEventReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationStatusEvent
        fields = ("to_status", "created_at")


class RegistrationReadSerializer(serializers.ModelSerializer):
    tournament_game = TournamentGameSummarySerializer(read_only=True)
    members = RegistrationMemberReadSerializer(many=True, read_only=True)
    status_events = RegistrationStatusEventReadSerializer(many=True, read_only=True)

    class Meta:
        model = Registration
        fields = (
            "id",
            "tournament_game",
            "team_name",
            "status",
            "fee_amount_snapshot",
            "fee_currency_snapshot",
            "submitted_at",
            "members",
            "status_events",
        )


class StrictFieldsSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            return super().to_internal_value(data)
        unknown_fields = set(data.keys()) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError(
                {field: "This field is not allowed." for field in sorted(unknown_fields)}
            )
        return super().to_internal_value(data)


class RegistrationMemberSubmissionSerializer(StrictFieldsSerializer):
    gamer_tag_snapshot = serializers.CharField(max_length=64)
    school_snapshot = serializers.CharField(max_length=128)
    is_captain = serializers.BooleanField()
    display_order = serializers.IntegerField(min_value=1)


class RegistrationSubmissionSerializer(StrictFieldsSerializer):
    tournament_game = serializers.PrimaryKeyRelatedField(
        queryset=TournamentGame.objects.all()
    )
    team_name = serializers.CharField(max_length=100, allow_blank=True)
    members = RegistrationMemberSubmissionSerializer(many=True)

    def to_member_inputs(self) -> list[RegistrationMemberInput]:
        return [
            RegistrationMemberInput(**member) for member in self.validated_data["members"]
        ]


class PaymentAttemptSubmissionSerializer(StrictFieldsSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    proof_file = serializers.FileField(required=False, allow_null=True)
    reference = serializers.CharField(max_length=128, allow_blank=True, required=False)


class PaymentAttemptReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAttempt
        fields = ("id", "status", "amount", "currency", "created_at")
