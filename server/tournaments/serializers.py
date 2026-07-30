from django.utils import timezone
from rest_framework import serializers

from registrations.models import Registration

from .models import Tournament, TournamentGame

_AVAILABILITY_TIME_CONTEXT_KEY = "public_tournament_availability_time"


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

    def _availability_time(self):
        if _AVAILABILITY_TIME_CONTEXT_KEY not in self.context:
            self.context[_AVAILABILITY_TIME_CONTEXT_KEY] = timezone.now()
        return self.context[_AVAILABILITY_TIME_CONTEXT_KEY]

    def get_registration_state(self, obj: TournamentGame) -> str:
        now = self._availability_time()
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
    cover_image = serializers.SerializerMethodField()
    is_featured = serializers.BooleanField(read_only=True)

    def get_cover_image(self, obj: Tournament) -> str | None:
      if not obj.cover_image:
        return None
      request = self.context.get('request')
      if request:
        return request.build_absolute_uri(obj.cover_image.url)
      return obj.cover_image.url

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
            "cover_image",
            "is_featured",
            "tournament_games",
        )
