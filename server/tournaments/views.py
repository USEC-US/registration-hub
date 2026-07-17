from django.db.models import Count, Prefetch, Q
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from registrations.models import Registration

from .models import Tournament, TournamentGame
from .serializers import PublicTournamentSerializer


class PublicTournamentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicTournamentSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        tournament_games = TournamentGame.objects.select_related("game").annotate(
            active_registration_count=Count(
                "registrations",
                filter=Q(
                    registrations__status__in=Registration.active_statuses()
                ),
            )
        )
        return (
            Tournament.objects.filter(is_published=True)
            .prefetch_related(
                Prefetch("tournament_games", queryset=tournament_games)
            )
            .order_by("starts_at", "name", "pk")
        )
