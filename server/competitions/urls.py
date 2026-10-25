from django.urls import path

from .views import (
    PublicCompetitionChangesView,
    PublicCompetitionView,
    PublicMatchView,
    PublicRoundView,
    PublicStageView,
)

urlpatterns = [
    path(
        "tournament-games/<int:division_id>/competition/",
        PublicCompetitionView.as_view(),
        name="public-competition",
    ),
    path(
        "tournament-games/<int:division_id>/competition/changes/",
        PublicCompetitionChangesView.as_view(),
        name="public-competition-changes",
    ),
    path(
        "competition-stages/<int:stage_id>/",
        PublicStageView.as_view(),
        name="public-competition-stage",
    ),
    path(
        "competition-rounds/<int:round_id>/",
        PublicRoundView.as_view(),
        name="public-competition-round",
    ),
    path(
        "competition-matches/<int:match_id>/",
        PublicMatchView.as_view(),
        name="public-competition-match",
    ),
]
