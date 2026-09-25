from rest_framework import serializers

from .models import ChangeSet, Match, MatchSlot, Round, Stage


class PublicEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    seed = serializers.IntegerField(read_only=True)
    display_name = serializers.CharField(source="entrant.display_name", read_only=True)
    display_tag = serializers.CharField(source="entrant.display_tag", read_only=True)


class PublicMatchSlotSerializer(serializers.Serializer):
    position = serializers.IntegerField(read_only=True)
    is_resolved = serializers.BooleanField(read_only=True)
    is_empty = serializers.SerializerMethodField()
    source_match_id = serializers.IntegerField(read_only=True, allow_null=True)
    entry = serializers.SerializerMethodField()

    def get_is_empty(self, obj: MatchSlot) -> bool:
        return obj.is_resolved and obj.resolved_entry_id is None

    def get_entry(self, obj: MatchSlot) -> dict | None:
        if obj.resolved_entry_id is None:
            return None
        return PublicEntrySerializer(obj.resolved_entry).data


class PublicMatchSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    number = serializers.IntegerField(read_only=True)
    scheduled_at = serializers.DateTimeField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)
    outcome = serializers.CharField(read_only=True)
    effective_series_length = serializers.IntegerField(read_only=True)
    side_one_score = serializers.IntegerField(read_only=True, allow_null=True)
    side_two_score = serializers.IntegerField(read_only=True, allow_null=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    historical = serializers.SerializerMethodField()
    winner = serializers.SerializerMethodField()
    slots = PublicMatchSlotSerializer(many=True, read_only=True)

    def get_historical(self, obj: Match) -> bool:
        return obj.round.draw.state == obj.round.draw.State.SUPERSEDED

    def get_winner(self, obj: Match) -> dict | None:
        if obj.winner_id is None:
            return None
        return PublicEntrySerializer(obj.winner).data


class PublicRoundSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    number = serializers.IntegerField(read_only=True)
    section = serializers.CharField(read_only=True)
    series_length_override = serializers.IntegerField(read_only=True, allow_null=True)
    matches = PublicMatchSerializer(many=True, read_only=True)


class PublicStageSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    sequence = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    format = serializers.CharField(read_only=True)
    series_mode = serializers.CharField(read_only=True)
    default_series_length = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    published_at = serializers.DateTimeField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_without_champion = serializers.BooleanField(read_only=True)
    champion = serializers.SerializerMethodField()
    entries = serializers.SerializerMethodField()
    rounds = serializers.SerializerMethodField()

    def _draw(self, obj: Stage):
        return next(
            (draw for draw in obj.draws.all() if draw.state == draw.State.PUBLISHED),
            None,
        )

    def get_champion(self, obj: Stage) -> dict | None:
        if obj.champion_id is None:
            return None
        return {
            "id": obj.champion_id,
            "display_name": obj.champion.display_name,
            "display_tag": obj.champion.display_tag,
        }

    def get_entries(self, obj: Stage) -> list[dict]:
        draw = self._draw(obj)
        return PublicEntrySerializer(draw.entries.all(), many=True).data if draw else []

    def get_rounds(self, obj: Stage) -> list[dict]:
        draw = self._draw(obj)
        return PublicRoundSerializer(draw.rounds.all(), many=True).data if draw else []


class PublicCompetitionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    competition_revision = serializers.IntegerField(source="revision", read_only=True)
    tournament_game_id = serializers.IntegerField(read_only=True)
    tournament_slug = serializers.CharField(
        source="tournament_game.tournament.slug", read_only=True
    )
    tournament_name = serializers.CharField(
        source="tournament_game.tournament.name", read_only=True
    )
    game_name = serializers.CharField(source="tournament_game.game.name", read_only=True)
    stages = PublicStageSerializer(many=True, read_only=True)


class PublicStageResponseSerializer(PublicStageSerializer):
    competition_revision = serializers.SerializerMethodField()

    def get_competition_revision(self, obj: Stage) -> int:
        return obj.competition.revision


class PublicRoundResponseSerializer(PublicRoundSerializer):
    competition_revision = serializers.SerializerMethodField()

    def get_competition_revision(self, obj: Round) -> int:
        return obj.draw.stage.competition.revision


class PublicMatchResponseSerializer(PublicMatchSerializer):
    competition_revision = serializers.SerializerMethodField()

    def get_competition_revision(self, obj: Match) -> int:
        return obj.round.draw.stage.competition.revision


class PublicChangeSerializer(serializers.Serializer):
    revision = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    kind = serializers.CharField(read_only=True)
    stage_id = serializers.IntegerField(read_only=True, required=False)
    draw_id = serializers.IntegerField(read_only=True, required=False)
    round_id = serializers.IntegerField(read_only=True, required=False)
    match_id = serializers.IntegerField(read_only=True, required=False)
    match_code = serializers.CharField(read_only=True, required=False)
    scheduled_at = serializers.DateTimeField(
        read_only=True, required=False, allow_null=True
    )
    series_length = serializers.IntegerField(
        read_only=True, required=False, allow_null=True
    )
    side_one_score = serializers.IntegerField(
        read_only=True, required=False, allow_null=True
    )
    side_two_score = serializers.IntegerField(
        read_only=True, required=False, allow_null=True
    )
    outcome = serializers.CharField(read_only=True, required=False)
    winner = serializers.CharField(read_only=True, required=False, allow_null=True)
    before = serializers.JSONField(read_only=True, required=False)
    after = serializers.JSONField(read_only=True, required=False)
    reset_matches = serializers.ListField(
        child=serializers.JSONField(), read_only=True, required=False
    )

    def to_representation(self, instance: ChangeSet) -> dict:
        return {
            "revision": instance.revision,
            "created_at": instance.created_at.isoformat(),
            **instance.public_data,
        }


class PublicCompetitionChangesResponseSerializer(serializers.Serializer):
    next = serializers.URLField(read_only=True, allow_null=True)
    previous = serializers.URLField(read_only=True, allow_null=True)
    competition_revision = serializers.IntegerField(read_only=True)
    results = PublicChangeSerializer(many=True, read_only=True)
