from rest_framework import serializers

from .models import ChangeSet, Match, MatchSlot, Round, Stage, TieResolution
from .round_robin_commands import group_standings


def _public_champion(entrant):
    if entrant is None:
        return None
    return {
        "id": entrant.pk,
        "display_name": entrant.display_name,
        "display_tag": entrant.display_tag,
    }


class PublicEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    seed = serializers.IntegerField(read_only=True)
    status = serializers.CharField(source="entrant.status", read_only=True)
    display_name = serializers.CharField(source="entrant.display_name", read_only=True)
    display_tag = serializers.CharField(source="entrant.display_tag", read_only=True)


class PublicMatchSlotSerializer(serializers.Serializer):
    position = serializers.IntegerField(read_only=True)
    is_resolved = serializers.BooleanField(read_only=True)
    is_empty = serializers.SerializerMethodField()
    source_match_id = serializers.IntegerField(read_only=True, allow_null=True)
    source_outcome = serializers.CharField(read_only=True)
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
    effective_series_mode = serializers.CharField(read_only=True)
    side_one_score = serializers.IntegerField(read_only=True, allow_null=True)
    side_two_score = serializers.IntegerField(read_only=True, allow_null=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    historical = serializers.SerializerMethodField()
    winner = serializers.SerializerMethodField()
    slots = PublicMatchSlotSerializer(many=True, read_only=True)

    def get_historical(self, obj: Match) -> bool:
        return (
            obj.round.state == Round.State.SUPERSEDED
            or obj.round.draw.state == obj.round.draw.State.SUPERSEDED
            or (
                obj.round.tie_resolution_id is not None
                and obj.round.tie_resolution.state == TieResolution.State.SUPERSEDED
            )
        )

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
    group_id = serializers.IntegerField(read_only=True, allow_null=True)
    tie_resolution_id = serializers.IntegerField(read_only=True, allow_null=True)
    effective_series_mode = serializers.SerializerMethodField()
    resting_entry = serializers.SerializerMethodField()

    def get_effective_series_mode(self, obj):
        return obj.series_mode_override or obj.draw.stage.series_mode

    def get_resting_entry(self, obj):
        if not obj.group_id:
            return None
        entries = (
            obj.tie_resolution.contenders.all()
            if obj.tie_resolution_id
            else obj.group.entries.all()
        )
        playing = {
            slot.resolved_entry_id for m in obj.matches.all() for slot in m.slots.all()
        }
        rest = next((entry for entry in entries if entry.pk not in playing), None)
        return PublicEntrySerializer(rest).data if rest else None


class PublicStageSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    sequence = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    format = serializers.CharField(read_only=True)
    grand_final_policy = serializers.CharField(read_only=True)
    series_mode = serializers.CharField(read_only=True)
    default_series_length = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    published_at = serializers.DateTimeField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_without_champion = serializers.BooleanField(read_only=True)
    champion = serializers.SerializerMethodField()
    entries = serializers.SerializerMethodField()
    rounds = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    round_robin_rules = serializers.SerializerMethodField()
    swiss_rules = serializers.SerializerMethodField()
    swiss_standings = serializers.SerializerMethodField()
    qualification = serializers.SerializerMethodField()
    draw_state = serializers.SerializerMethodField()
    lifecycle_state = serializers.SerializerMethodField()

    def get_lifecycle_state(self, obj):
        if self._draw(obj) is None:
            return "RETIRED"
        return "CLOSED" if obj.competition.ended_at else "OPEN"

    def _display_draw(self, obj):
        return self._draw(obj) or next(
            (
                d
                for d in sorted(obj.draws.all(), key=lambda d: d.pk, reverse=True)
                if d.published_at is not None
            ),
            None,
        )

    def get_draw_state(self, obj):
        return "PUBLISHED" if self._draw(obj) else "AWAITING_REPLACEMENT"

    def get_qualification(self, obj):
        if (
            obj.format not in (Stage.Format.ROUND_ROBIN, Stage.Format.SWISS_THRESHOLD)
            and obj.advancement_count is None
        ):
            return None
        draw = self._draw(obj)
        result = {
            "state": "PROVISIONAL",
            "advance_count": obj.advancement_count,
            "qualifiers": [],
            "placement_bands": [],
            "cutoff_ties": [],
            "block_reason": None,
        }
        if draw is None:
            return result
        from .qualification import stage_qualification

        draw._qualification_matches = [
            m
            for r in self._rounds(draw)
            if r.state == Round.State.PUBLISHED
            for m in r.matches.all()
        ]
        state = stage_qualification(draw)
        entries = {e.pk: PublicEntrySerializer(e).data for e in draw.entries.all()}
        rounds = self._rounds(draw)
        resolutions = {r.pk: r for r in draw.tie_resolutions.all()}
        ties = []
        for cutoff in state["cutoffs"]:
            resolution = resolutions.get(cutoff["resolution_id"])
            ties.append(
                {
                    "group_id": cutoff["group_id"],
                    "places": cutoff["places"],
                    "tied_entries": [entries[i] for i in cutoff["entry_ids"]],
                    "resolution_id": cutoff["resolution_id"],
                    "parent_id": cutoff["parent_resolution_id"],
                    "method": resolution.method if resolution else None,
                    "state": resolution.state if resolution else "AWAITING_RESOLUTION",
                    "ordered_entries": [entries[i] for i in resolution.decision_order]
                    if resolution
                    else [],
                    "round_ids": [
                        r.pk
                        for r in rounds
                        if resolution and r.tie_resolution_id == resolution.pk
                    ],
                }
            )
        represented = {cutoff["resolution_id"] for cutoff in state["cutoffs"]}
        if obj.format != Stage.Format.ROUND_ROBIN:
            for resolution in resolutions.values():
                if resolution.pk in represented:
                    continue
                ties.append(
                    {
                        "group_id": None,
                        "places": resolution.places,
                        "tied_entries": [
                            entries[e.pk] for e in resolution.contenders.all()
                        ],
                        "resolution_id": resolution.pk,
                        "parent_id": resolution.parent_id,
                        "method": resolution.method,
                        "state": resolution.state,
                        "ordered_entries": [
                            entries[i] for i in resolution.decision_order
                        ],
                        "round_ids": [
                            r.pk for r in rounds if r.tie_resolution_id == resolution.pk
                        ],
                    }
                )
        return {
            **result,
            "state": state["qualification_state"],
            "qualifiers": [entries[i] for i in state["qualifier_entry_ids"]],
            "placement_bands": [[entries[i] for i in band] for band in state["bands"]],
            "cutoff_ties": ties,
            "block_reason": state["block_reason"],
        }

    def get_swiss_rules(self, obj):
        if obj.format not in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
            return None
        draw = self._draw(obj)
        return {
            "round_policy": "THRESHOLD"
            if obj.format == Stage.Format.SWISS_THRESHOLD
            else "CUSTOM"
            if obj.swiss_round_count is not None
            else "AUTOMATIC",
            "round_limit": draw.swiss_round_limit if draw else None,
            "win_target": obj.swiss_win_target,
            "loss_limit": obj.swiss_loss_limit,
            "win_points": str(obj.win_points),
            "draw_points": str(obj.draw_points),
            "loss_points": str(obj.loss_points),
            "tiebreaks": obj.tiebreaks,
        }

    def get_swiss_standings(self, obj):
        draw = self._draw(obj)
        if not draw or obj.format not in (
            Stage.Format.SWISS_FIXED,
            Stage.Format.SWISS_THRESHOLD,
        ):
            return []
        from .swiss_commands import swiss_standings

        entries = {e.pk: PublicEntrySerializer(e).data for e in draw.entries.all()}
        matches = [m for r in self._rounds(draw) for m in r.matches.all()]
        return [
            {
                "entry": entries[row.entry_id],
                "rank": row.rank,
                "played": row.played,
                "wins": row.wins,
                "draws": row.draws,
                "losses": row.losses,
                "points": f"{row.points:.2f}",
                "games_won": row.games_won,
                "game_difference": row.game_difference,
                "opponent_points": f"{row.opponent_points:.2f}",
                "bye_count": row.bye_count,
                "status": row.status,
            }
            for row in swiss_standings(draw, projected_matches=matches)
        ]

    def get_round_robin_rules(self, obj):
        if obj.format != Stage.Format.ROUND_ROBIN:
            return None
        return {
            "meetings": obj.round_robin_meetings,
            "win_points": str(obj.win_points),
            "draw_points": str(obj.draw_points),
            "loss_points": str(obj.loss_points),
            "tiebreaks": obj.tiebreaks,
        }

    def get_groups(self, obj):
        draw = self._draw(obj)
        if not draw or obj.format != Stage.Format.ROUND_ROBIN:
            return []
        rounds = self._rounds(draw)
        result = []
        for group in draw.groups.all():
            group_rounds = [r for r in rounds if r.group_id == group.pk]
            group._standings_matches = [
                m
                for r in group_rounds
                if r.state == Round.State.PUBLISHED
                for m in r.matches.all()
            ]
            state = group_standings(group)
            entries = {
                entry.pk: PublicEntrySerializer(entry).data
                for entry in group.entries.all()
            }
            tied = {pk for tie in state["cutoff_ties"] for pk in tie["entry_ids"]}
            standings = [
                {
                    "entry": entries[row.entry_id],
                    "rank": row.rank,
                    "played": row.played,
                    "wins": row.wins,
                    "draws": row.draws,
                    "losses": row.losses,
                    "points": f"{row.points:.2f}",
                    "games_won": row.games_won,
                    "game_difference": row.game_difference,
                    "qualification": "PROVISIONAL"
                    if state["qualification_state"] == "PROVISIONAL"
                    else "QUALIFIED"
                    if row.entry_id in state["qualifiers"]
                    else "TIED"
                    if row.entry_id in tied
                    else "NOT_QUALIFIED",
                }
                for row in state["standings"]
            ]
            ties = [
                {
                    "id": tie.pk,
                    "parent_id": tie.parent_id,
                    "method": tie.method,
                    "state": tie.state,
                    "places": tie.places,
                    "tied_entries": [entries[e.pk] for e in tie.contenders.all()],
                    "ordered_entries": [entries[pk] for pk in tie.decision_order],
                    "round_ids": [
                        r.pk for r in group_rounds if r.tie_resolution_id == tie.pk
                    ],
                }
                for tie in group.tie_resolutions.all()
            ]
            result.append(
                {
                    "id": group.pk,
                    "number": group.number,
                    "name": group.name,
                    "qualifying_places": group.qualifying_places,
                    "entries": list(entries.values()),
                    "round_ids": [r.pk for r in group_rounds],
                    "standings": standings,
                    "qualifiers": [entries[pk] for pk in state["qualifiers"]],
                    "qualification_state": state["qualification_state"],
                    "tie_resolutions": ties,
                }
            )
        return result

    def _draw(self, obj: Stage):
        return next(
            (draw for draw in obj.draws.all() if draw.state == draw.State.PUBLISHED),
            None,
        )

    def get_champion(self, obj: Stage) -> dict | None:
        if (
            obj.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)
            or obj.champion_id is None
        ):
            return None
        return {
            "id": obj.champion_id,
            "display_name": obj.champion.display_name,
            "display_tag": obj.champion.display_tag,
        }

    def get_entries(self, obj: Stage) -> list[dict]:
        draw = self._display_draw(obj)
        return PublicEntrySerializer(draw.entries.all(), many=True).data if draw else []

    def get_rounds(self, obj: Stage) -> list[dict]:
        draw = self._display_draw(obj)
        return PublicRoundSerializer(self._rounds(draw), many=True).data if draw else []

    def _rounds(self, draw):
        return [
            r
            for r in draw.rounds.all()
            if r.published_at is not None
            and (
                r.state == Round.State.PUBLISHED
                or draw.state == draw.State.SUPERSEDED
                or (
                    r.state == Round.State.SUPERSEDED
                    and r.section == Round.Section.TIEBREAK
                    and draw.stage.format
                    not in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)
                )
            )
        ]


class PublicCompetitionSerializer(serializers.Serializer):
    ending = serializers.SerializerMethodField()

    def get_ending(self, obj):
        if obj.ended_at is None:
            return None
        return {
            "stage_id": obj.ended_stage_id,
            "ended_at": obj.ended_at.isoformat(),
            "champion": _public_champion(obj.ended_champion),
        }

    id = serializers.IntegerField(read_only=True)
    competition_revision = serializers.IntegerField(source="revision", read_only=True)
    tournament_game_id = serializers.IntegerField(read_only=True)
    tournament_slug = serializers.CharField(
        source="tournament_game.tournament.slug", read_only=True
    )
    tournament_name = serializers.CharField(
        source="tournament_game.tournament.name", read_only=True
    )
    game_name = serializers.CharField(
        source="tournament_game.game.name", read_only=True
    )
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
    reset_final_changes = serializers.ListField(
        child=serializers.JSONField(), read_only=True, required=False
    )

    round_number = serializers.IntegerField(read_only=True, required=False)
    match_ids = serializers.ListField(
        child=serializers.IntegerField(), read_only=True, required=False
    )
    rematch_count = serializers.IntegerField(read_only=True, required=False)
    repeated_bye = serializers.BooleanField(read_only=True, required=False)
    automatic_results = serializers.ListField(
        child=serializers.JSONField(), read_only=True, required=False
    )
    swiss_impact = serializers.JSONField(read_only=True, required=False)
    entrant_id = serializers.IntegerField(read_only=True, required=False)
    display_name = serializers.CharField(read_only=True, required=False)
    retired_draws = serializers.ListField(
        child=serializers.IntegerField(), read_only=True, required=False
    )
    retired_rounds = serializers.ListField(
        child=serializers.IntegerField(), read_only=True, required=False
    )
    reset_match_ids = serializers.ListField(
        child=serializers.IntegerField(), read_only=True, required=False
    )
    match_impacts = serializers.ListField(
        child=serializers.JSONField(), read_only=True, required=False
    )

    def to_representation(self, instance: ChangeSet) -> dict:
        allowed = {
            "kind",
            "stage_id",
            "draw_id",
            "source_stage_id",
            "round_id",
            "round_number",
            "match_ids",
            "rematch_count",
            "repeated_bye",
            "match_id",
            "match_code",
            "scheduled_at",
            "series_length",
            "side_one_score",
            "side_two_score",
            "outcome",
            "winner",
            "group_id",
            "group_name",
            "resolution_id",
            "method",
            "places",
            "tied_entries",
            "ordered_entries",
        }
        snapshot_fields = {
            "match_id",
            "match_code",
            "status",
            "outcome",
            "side_one",
            "side_two",
            "side_one_score",
            "side_two_score",
            "winner",
            "applied_series_length",
            "applied_series_mode",
            "started_at",
            "completed_at",
        }
        public_data = {
            key: value for key, value in instance.public_data.items() if key in allowed
        }
        for key in ("before", "after"):
            if key in instance.public_data:
                public_data[key] = {
                    field: value
                    for field, value in instance.public_data[key].items()
                    if field in snapshot_fields and not isinstance(value, (dict, list))
                }
        for key in ("reset_matches", "automatic_results"):
            if key not in instance.public_data:
                continue
            public_data[key] = [
                {
                    field: value
                    for field, value in snapshot.items()
                    if field in snapshot_fields and not isinstance(value, (dict, list))
                }
                for snapshot in instance.public_data[key]
            ]
        if "reset_final_changes" in instance.public_data:
            public_data["reset_final_changes"] = [
                {
                    field: value
                    for field, value in change.items()
                    if field in {"match_id", "match_code", "before", "after"}
                }
                for change in instance.public_data["reset_final_changes"]
            ]
        impact = instance.public_data.get("group_impact")
        if impact:
            fields = {
                "entry_id",
                "rank",
                "played",
                "wins",
                "draws",
                "losses",
                "points",
                "games_won",
                "game_difference",
            }
            public_data["group_impact"] = {
                key: impact[key]
                for key in (
                    "group_id",
                    "group_name",
                    "invalidated_resolution_ids",
                    "revalidated_resolution_ids",
                )
            }
            for key in ("before", "after"):
                public_data["group_impact"][key] = {
                    "qualification_state": impact[key]["qualification_state"],
                    "qualifiers": impact[key]["qualifiers"],
                    "standings": [
                        {k: v for k, v in row.items() if k in fields}
                        for row in impact[key]["standings"]
                    ],
                }
            public_data["group_impact"]["historical_matches"] = [
                {
                    k: v
                    for k, v in snapshot.items()
                    if k in snapshot_fields and not isinstance(v, (dict, list))
                }
                for snapshot in impact["historical_matches"]
            ]
        swiss = instance.public_data.get("swiss_impact")
        if swiss is not None:
            public_data["swiss_impact"] = {
                key: swiss[key]
                for key in ("retired_round_ids", "retired_match_ids")
                if key in swiss
            }
        handoff = instance.public_data.get("handoff_impact")
        if handoff:
            public_data["handoff_impact"] = {
                "retired_draws": [
                    {k: v for k, v in item.items() if k in {"stage_id", "draw_id"}}
                    for item in handoff.get("retired_draws", [])
                ],
                "reset_matches": [
                    {
                        k: v
                        for k, v in item.items()
                        if k in snapshot_fields | {"stage_id", "draw_id"}
                    }
                    for item in handoff.get("reset_matches", [])
                ],
            }
        if instance.kind in {
            "entrant_withdrawn",
            "entrant_disqualified",
            "entrant_restored",
            "entrant_status_changed",
            "competition_ended",
            "competition_reopened",
        }:
            for key in (
                "entrant_id",
                "display_name",
                "retired_draws",
                "retired_rounds",
                "reset_match_ids",
            ):
                if key in instance.public_data:
                    public_data[key] = instance.public_data[key]
            for key in ("before", "after"):
                value = instance.public_data.get(key, {})
                if instance.kind.startswith("entrant_"):
                    public_data[key] = {"status": value["status"]}
                else:
                    champion = instance.competition.entrants.filter(
                        pk=value.get("champion_id")
                    ).first()
                    public_data[key] = {
                        "stage_id": value.get("stage_id"),
                        "ended_at": value.get("ended_at"),
                        "champion": _public_champion(champion),
                    }
            public_match_ids = set(
                Match.objects.filter(
                    pk__in=[
                        item["match_id"]
                        for item in instance.public_data.get("match_impacts", [])
                    ],
                    round__draw__stage__competition_id=instance.competition_id,
                    round__published_at__isnull=False,
                    round__draw__published_at__isnull=False,
                ).values_list("pk", flat=True)
            )
            public_data["match_impacts"] = [
                {
                    "match_id": item["match_id"],
                    **{
                        key: {
                            k: v
                            for k, v in item.get(key, {}).items()
                            if k in snapshot_fields | {"frozen"}
                            and not isinstance(v, (dict, list))
                        }
                        for key in ("before", "after")
                    },
                }
                for item in instance.public_data.get("match_impacts", [])
                if item["match_id"] in public_match_ids
            ]
        return {
            "revision": instance.revision,
            "created_at": instance.created_at.isoformat(),
            **public_data,
        }


class PublicCompetitionChangesResponseSerializer(serializers.Serializer):
    next = serializers.URLField(read_only=True, allow_null=True)
    previous = serializers.URLField(read_only=True, allow_null=True)
    competition_revision = serializers.IntegerField(read_only=True)
    results = PublicChangeSerializer(many=True, read_only=True)
