from django.db.models import Count, Prefetch, Q
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from registrations.reservations import active_registrations
from django.utils import timezone

from .models import Tournament, TournamentGame
from .serializers import PublicTournamentSerializer, _AVAILABILITY_TIME_CONTEXT_KEY


class PublicTournamentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicTournamentSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def _availability_time(self):
        if not hasattr(self, "_availability_now"):
            self._availability_now = timezone.now()
        return self._availability_now

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            _AVAILABILITY_TIME_CONTEXT_KEY: self._availability_time(),
        }

    def get_queryset(self):
        tournament_games = TournamentGame.objects.select_related("game").annotate(
            active_registration_count=Count(
                "registrations",
                filter=Q(
                    registrations__in=active_registrations(
                        now=self._availability_time()
                    ).values("pk")
                ),
            )
        )
        return (
            Tournament.objects.filter(is_published=True)
            .prefetch_related(Prefetch("tournament_games", queryset=tournament_games))
            .order_by("-is_featured", "starts_at", "name", "pk")
        )
