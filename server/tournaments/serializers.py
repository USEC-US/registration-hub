from django.utils import timezone
from rest_framework import serializers

from registrations.models import Registration

from .models import Tournament, TournamentGame


class PublicTournamentGameSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source="game.name", read_only=True)
    game_slug = serializers.CharField(source="game.slug", read_only=True)
    registration_state = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()
    capacity_remaining = serializers.SerializerMethodField()

    class Meta:
        model = TournamentGame
        fields = (
            "id",
            "game_name",
            "game_slug",
            "team_size_min",
            "team_size_max",
            "registration_opens_at",
            "registration_closes_at",
            "registration_capacity",
            "capacity_remaining",
            "fee_amount",
            "fee_currency",
            "registration_state",
            "is_registration_open",
        )

    def _active_count(self, obj: TournamentGame) -> int:
        if hasattr(obj, "active_registration_count"):
            return obj.active_registration_count
        return obj.registrations.filter(
            status__in=Registration.active_statuses()
        ).count()

    def get_capacity_remaining(self, obj: TournamentGame) -> int | None:
        if obj.registration_capacity is None:
            return None
        return max(obj.registration_capacity - self._active_count(obj), 0)

    def get_registration_state(self, obj: TournamentGame) -> str:
        now = timezone.now()
        if now < obj.registration_opens_at:
            return "not_open"
        if now >= obj.registration_closes_at:
            return "closed"
        if self.get_capacity_remaining(obj) == 0:
            return "full"
        return "open"

    def get_is_registration_open(self, obj: TournamentGame) -> bool:
        return self.get_registration_state(obj) == "open"


class PublicTournamentSerializer(serializers.ModelSerializer):
    tournament_games = PublicTournamentGameSerializer(many=True, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "starts_at",
            "ends_at",
            "location",
            "tournament_games",
        )
