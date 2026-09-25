from contextlib import contextmanager

from drf_spectacular.utils import extend_schema
from django.db import connection, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChangeSet, Competition, Match, MatchSlot, Round, Stage, StageDraw
from .serializers import (
    PublicChangeSerializer,
    PublicCompetitionChangesResponseSerializer,
    PublicCompetitionSerializer,
    PublicMatchResponseSerializer,
    PublicRoundResponseSerializer,
    PublicStageResponseSerializer,
)


@contextmanager
def consistent_public_read():
    if connection.in_atomic_block:
        yield
        return
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
        yield


def _published_match_queryset():
    slots = MatchSlot.objects.select_related("resolved_entry__entrant").order_by(
        "position"
    )
    return Match.objects.select_related(
        "round__draw__stage__competition", "winner__entrant"
    ).prefetch_related(Prefetch("slots", queryset=slots))


def _published_round_queryset():
    return Round.objects.prefetch_related(
        Prefetch("matches", queryset=_published_match_queryset())
    )


def _published_stage_queryset():
    draws = StageDraw.objects.filter(state=StageDraw.State.PUBLISHED).prefetch_related(
        "entries__entrant",
        Prefetch("rounds", queryset=_published_round_queryset()),
    )
    return Stage.objects.filter(published_at__isnull=False).select_related(
        "competition", "champion"
    ).prefetch_related(Prefetch("draws", queryset=draws))


def _published_competition_queryset():
    return Competition.objects.filter(
        tournament_game__tournament__is_published=True,
        stages__published_at__isnull=False,
    ).select_related(
        "tournament_game__tournament", "tournament_game__game"
    ).prefetch_related(Prefetch("stages", queryset=_published_stage_queryset())).distinct()


class PublicCompetitionView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicCompetitionSerializer)
    def get(self, request, division_id: int):
        with consistent_public_read():
            competition = get_object_or_404(
                _published_competition_queryset(), tournament_game_id=division_id
            )
            return Response(PublicCompetitionSerializer(competition).data)


class PublicStageView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicStageResponseSerializer)
    def get(self, request, stage_id: int):
        with consistent_public_read():
            stage = get_object_or_404(
                _published_stage_queryset().filter(
                    competition__tournament_game__tournament__is_published=True
                ),
                pk=stage_id,
            )
            return Response(PublicStageResponseSerializer(stage).data)


class PublicRoundView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicRoundResponseSerializer)
    def get(self, request, round_id: int):
        with consistent_public_read():
            round_ = get_object_or_404(
                _published_round_queryset().filter(
                    draw__state=StageDraw.State.PUBLISHED,
                    draw__stage__published_at__isnull=False,
                    draw__stage__competition__tournament_game__tournament__is_published=True,
                ),
                pk=round_id,
            )
            return Response(PublicRoundResponseSerializer(round_).data)


class PublicMatchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicMatchResponseSerializer)
    def get(self, request, match_id: int):
        with consistent_public_read():
            match = get_object_or_404(
                _published_match_queryset().filter(
                    round__draw__published_at__isnull=False,
                    round__draw__stage__published_at__isnull=False,
                    round__draw__stage__competition__tournament_game__tournament__is_published=True,
                ),
                pk=match_id,
            )
            return Response(PublicMatchResponseSerializer(match).data)


class PublicChangesPagination(CursorPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-revision"


class PublicCompetitionChangesView(APIView):
    permission_classes = [AllowAny]
    pagination_class = PublicChangesPagination

    @extend_schema(responses=PublicCompetitionChangesResponseSerializer)
    def get(self, request, division_id: int):
        with consistent_public_read():
            competition = get_object_or_404(
                _published_competition_queryset(), tournament_game_id=division_id
            )
            queryset = ChangeSet.objects.filter(
                competition=competition,
                public_data__has_key="kind",
            ).order_by("-revision")
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(queryset, request, view=self)
            response = paginator.get_paginated_response(
                PublicChangeSerializer(page, many=True).data
            )
            response.data["competition_revision"] = competition.revision
            return response
