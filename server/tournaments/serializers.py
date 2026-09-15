from django.utils import timezone
from django.core.exceptions import ValidationError
from registrations.models import PaymentSettings
from registrations.vietqr import build_vietqr
from rest_framework import serializers

from registrations.reservations import active_registrations

from .models import Tournament, TournamentGame

_AVAILABILITY_TIME_CONTEXT_KEY = "public_tournament_availability_time"


class PublicTournamentGameSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source="game.name", read_only=True)
    game_slug = serializers.CharField(source="game.slug", read_only=True)
    registration_state = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()
    capacity_remaining = serializers.SerializerMethodField()
    payment_hold_minutes = serializers.SerializerMethodField()
    payment_available = serializers.SerializerMethodField()

    class Meta:
        model = TournamentGame
        fields = (
            "id",
            "game_name",
            "game_slug",
            "main_roster_size",
            "substitute_limit",
            "registration_opens_at",
            "registration_closes_at",
            "registration_capacity",
            "capacity_remaining",
            "fee_amount",
            "fee_currency",
            "payment_hold_minutes",
            "payment_available",
            "registration_state",
            "is_registration_open",
        )

    def _payment_settings(self):
        key = "public_payment_settings"
        if key not in self.context:
            self.context[key] = PaymentSettings.objects.filter(pk=1).first()
        return self.context[key]

    def get_payment_hold_minutes(self, obj: TournamentGame) -> int:
        settings = self._payment_settings()
        return settings.payment_hold_minutes if settings else 60

    def get_payment_available(self, obj: TournamentGame) -> bool:
        if obj.fee_amount <= 0:
            return True
        settings = self._payment_settings()
        if settings is None or not settings.enabled or obj.fee_currency != "VND":
            return False
        try:
            # This is a read of an existing singleton. Field/destination validation
            # is local; its unique/check constraints already hold in the database.
            settings.full_clean(validate_unique=False, validate_constraints=False)
            build_vietqr(
                bank_bin=settings.bank_bin,
                account_number=settings.account_number,
                amount=obj.fee_amount,
                transfer_content="",
            )
        except ValidationError:
            return False
        return True

    def _active_count(self, obj: TournamentGame) -> int:
        if hasattr(obj, "active_registration_count"):
            return obj.active_registration_count
        return (
            active_registrations(now=self._availability_time())
            .filter(tournament_game=obj)
            .count()
        )

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
        request = self.context.get("request")
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
            "students_only",
            "tournament_games",
        )
