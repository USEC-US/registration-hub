import hashlib
import json
import secrets
from collections.abc import Sequence
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core import signing
from django.db import transaction
from django.utils import timezone
from itertools import groupby

from config.organizers import require_organizer
from .command_support import (
    MAX_ENTRANTS,
    MAX_MATCHES,
    _check_revision,
    _lock_competition,
    _match_snapshot,
    _record_change,
    _validate_series_length,
    _stage_for_command,
    _validate_stage_sequence,
)
from .models import (
    CompetitionEntrant,
    Match,
    MatchSlot,
    Round,
    Stage,
    StageDraw,
    StageEntry,
    StageGroup,
    StageGroupPlan,
    TieResolution,
)
from .round_robin import (
    DEFAULT_TIEBREAKS,
    TIEBREAKS,
    allocate_snake_groups,
    generate_round_robin,
    rank_group,
    RoundRobinResult,
)


def _results(matches):
    results = []
    for match in matches:
        slots = list(match.slots.all())
        results.append(
            RoundRobinResult(
                match.pk,
                slots[0].resolved_entry_id,
                slots[1].resolved_entry_id,
                match.outcome,
                match.side_one_score,
                match.side_two_score,
                match.winner_id,
            )
        )
    return results


def _fingerprint(results, *, points, tiebreaks, source=""):
    game_metrics = bool(set(tiebreaks) & {"GAME_DIFFERENCE", "GAMES_WON"})
    inputs = [
        [
            r.match_id,
            r.side_one_id,
            r.side_two_id,
            r.winner_id,
            "DOUBLE_FORFEIT"
            if r.outcome == "DOUBLE_FORFEIT"
            else "WIN"
            if r.winner_id
            else "DRAW",
            r.side_one_score if game_metrics and r.outcome == "PLAYED" else None,
            r.side_two_score if game_metrics and r.outcome == "PLAYED" else None,
        ]
        for r in results
    ]
    return hashlib.sha256(
        json.dumps(
            [source, list(map(str, points)), list(tiebreaks), inputs],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def group_standings(group: StageGroup, *, replacement=None) -> dict:
    stage = group.draw.stage
    entry_ids = [entry.pk for entry in group.entries.all()]
    matches = getattr(group, "_standings_matches", None)
    if matches is None:
        matches = list(
            Match.objects.filter(round__group=group)
            .select_related("round")
            .prefetch_related("slots")
        )
    ordinary = [m for m in matches if m.round.section == Round.Section.NORMAL]

    def results_for(items):
        results = _results([m for m in items if m.status == Match.Status.FINAL])
        if replacement:
            results = [
                replace(r, **replacement[1]) if r.match_id == replacement[0] else r
                for r in results
            ]
        return results

    ordinary_results = results_for(ordinary)
    points = (stage.win_points, stage.draw_points, stage.loss_points)
    rows = rank_group(
        entry_ids,
        ordinary_results,
        points=points,
        tiebreaks=stage.tiebreaks,
    )
    complete = all(m.status == Match.Status.FINAL for m in ordinary)
    resolutions = list(group.tie_resolutions.all())
    fingerprint = _fingerprint(
        ordinary_results, points=points, tiebreaks=stage.tiebreaks
    )
    states = {}
    ties = []

    def select(ranked, cutoff, source, parent=None):
        selected = []
        for rank, block in groupby(ranked, key=lambda row: row.rank):
            ids = [row.entry_id for row in block]
            if rank <= cutoff:
                places = cutoff - rank + 1
                if places < len(ids):
                    resolution = next(
                        (
                            r
                            for r in resolutions
                            if r.parent_id == parent
                            and r.state != TieResolution.State.SUPERSEDED
                            and r.source_fingerprint == source
                            and r.places == places
                            and {e.pk for e in r.contenders.all()} == set(ids)
                        ),
                        None,
                    )
                    if resolution is None:
                        ties.append(
                            {
                                "entry_ids": ids,
                                "places": places,
                                "parent_resolution_id": parent,
                                "resolution_id": None,
                                "source_fingerprint": source,
                            }
                        )
                    elif resolution.method == TieResolution.Method.MANUAL:
                        selected.extend(resolution.decision_order[:places])
                        states[resolution.pk] = TieResolution.State.CONFIRMED
                    else:
                        extra = [
                            m
                            for m in matches
                            if m.round.tie_resolution_id == resolution.pk
                        ]
                        if not extra or any(
                            m.status != Match.Status.FINAL for m in extra
                        ):
                            states[resolution.pk] = TieResolution.State.PENDING
                            ties.append(
                                {
                                    "entry_ids": ids,
                                    "places": places,
                                    "parent_resolution_id": parent,
                                    "resolution_id": resolution.pk,
                                    "source_fingerprint": source,
                                }
                            )
                        else:
                            extra_results = results_for(extra)
                            extra_rules = ("HEAD_TO_HEAD", "GAME_DIFFERENCE")
                            extra_rows = rank_group(
                                ids,
                                extra_results,
                                points=(Decimal(1), Decimal(0), Decimal(0)),
                                tiebreaks=extra_rules,
                            )
                            extra_source = _fingerprint(
                                extra_results,
                                points=(1, 0, 0),
                                tiebreaks=extra_rules,
                                source=source,
                            )
                            count = len(ties)
                            selected.extend(
                                select(extra_rows, places, extra_source, resolution.pk)
                            )
                            states[resolution.pk] = (
                                TieResolution.State.CONFIRMED
                                if len(ties) == count
                                else TieResolution.State.AWAITING_RESOLUTION
                            )
                else:
                    selected.extend(ids)
        return selected

    qualifiers = select(rows, group.qualifying_places, fingerprint) if complete else []
    return {
        "standings": rows,
        "qualifiers": qualifiers,
        "cutoff_ties": ties,
        "resolution_states": states,
        "qualification_state": "PROVISIONAL"
        if not complete
        else "AWAITING_RESOLUTION"
        if ties
        else "RESOLVED",
    }


def update_round_robin_completion(draw: StageDraw) -> None:
    states = [group_standings(group) for group in draw.groups.all()]
    for state in states:
        for resolution_id, status in state["resolution_states"].items():
            TieResolution.objects.filter(pk=resolution_id).update(
                state=status,
                confirmed_at=timezone.now()
                if status == TieResolution.State.CONFIRMED
                else None,
            )
    stage = draw.stage
    if states and all(state["qualification_state"] == "RESOLVED" for state in states):
        stage.status = Stage.Status.COMPLETE
        stage.completed_at = stage.completed_at or timezone.now()
        group = draw.groups.first()
        champion_id = (
            states[0]["qualifiers"][0]
            if len(states) == 1 and group.qualifying_places == 1
            else None
        )
        stage.champion_id = (
            draw.entries.get(pk=champion_id).entrant_id if champion_id else None
        )
    else:
        stage.status = (
            Stage.Status.AWAITING
            if states
            and all(state["qualification_state"] != "PROVISIONAL" for state in states)
            else Stage.Status.IN_PROGRESS
            if Match.objects.filter(round__draw=draw, started_at__isnull=False).exists()
            else Stage.Status.READY
        )
        stage.completed_at = None
        stage.champion = None
    stage.completed_without_champion = False
    stage.save(
        update_fields=(
            "status",
            "completed_at",
            "champion",
            "completed_without_champion",
        )
    )


TIE_SALT = "competitions.group_tie"


def _tie_payload(
    group,
    *,
    expected_revision,
    tied_entry_ids,
    method,
    ordered_entry_ids=(),
    series_length=1,
    parent_resolution_id=None,
):
    _check_revision(group.draw.stage.competition, expected_revision)
    if group.draw.state != StageDraw.State.PUBLISHED:
        raise ValidationError("Only published groups can resolve qualification ties.")
    state = group_standings(group)
    tie = next(
        (
            tie
            for tie in state["cutoff_ties"]
            if set(tie["entry_ids"]) == set(tied_entry_ids)
            and tie["parent_resolution_id"] == parent_resolution_id
            and tie["resolution_id"] is None
        ),
        None,
    )
    if tie is None or len(set(tied_entry_ids)) != len(tied_entry_ids):
        raise ValidationError(
            "This cutoff is not awaiting the submitted tie choice. Reload standings."
        )
    if method not in TieResolution.Method.values:
        raise ValidationError("Choose an organizer decision or extra matches.")
    if method == TieResolution.Method.MANUAL:
        if len(ordered_entry_ids) != len(tied_entry_ids) or set(
            ordered_entry_ids
        ) != set(tied_entry_ids):
            raise ValidationError("Order every tied entrant exactly once.")
    else:
        if ordered_entry_ids:
            raise ValidationError("Extra matches do not use a manual order.")
        _validate_series_length(Stage.SeriesMode.BEST_OF, series_length)
        count = len(tied_entry_ids) * (len(tied_entry_ids) - 1) // 2
        existing = Match.objects.filter(
            round__draw=group.draw, round__section=Round.Section.TIEBREAK
        ).count()
        if existing + count > MAX_MATCHES:
            raise ValidationError(
                "The extra-match budget is exhausted. Use an organizer decision."
            )
    return {
        "group_id": group.pk,
        "competition_id": group.draw.stage.competition_id,
        "revision": expected_revision,
        "tied_entry_ids": tie["entry_ids"],
        "places": tie["places"],
        "source_fingerprint": tie["source_fingerprint"],
        "method": method,
        "ordered_entry_ids": list(ordered_entry_ids),
        "series_length": series_length,
        "parent_resolution_id": parent_resolution_id,
    }


def preview_group_tie(
    *,
    actor,
    group_id,
    expected_revision,
    tied_entry_ids,
    method,
    ordered_entry_ids=(),
    series_length=1,
    parent_resolution_id=None,
):
    require_organizer(actor, "competitions.change_competition")
    group = StageGroup.objects.select_related("draw__stage__competition").get(
        pk=group_id
    )
    payload = _tie_payload(
        group,
        expected_revision=expected_revision,
        tied_entry_ids=tied_entry_ids,
        method=method,
        ordered_entry_ids=ordered_entry_ids,
        series_length=series_length,
        parent_resolution_id=parent_resolution_id,
    )
    fixtures = (
        [asdict(r) for r in generate_round_robin(payload["tied_entry_ids"], meetings=1)]
        if method == TieResolution.Method.EXTRA_MATCHES
        else []
    )
    return {
        **payload,
        "fixtures": fixtures,
        "token": signing.dumps(payload, salt=TIE_SALT, compress=True),
    }


def confirm_group_tie(*, actor, token, internal_reason=""):
    require_organizer(actor, "competitions.change_competition")
    try:
        submitted = signing.loads(token, salt=TIE_SALT, max_age=3600)
    except signing.BadSignature as error:
        raise ValidationError("The tie preview is invalid or expired.") from error
    if (
        submitted["method"] == TieResolution.Method.MANUAL
        and not internal_reason.strip()
    ):
        raise ValidationError(
            "An internal reason is required for an organizer decision."
        )
    with transaction.atomic():
        competition = _lock_competition(submitted["competition_id"])
        group = (
            StageGroup.objects.select_for_update()
            .select_related("draw__stage")
            .get(pk=submitted["group_id"])
        )
        group.draw.stage.competition = competition
        current = _tie_payload(
            group,
            expected_revision=submitted["revision"],
            tied_entry_ids=submitted["tied_entry_ids"],
            method=submitted["method"],
            ordered_entry_ids=submitted["ordered_entry_ids"],
            series_length=submitted["series_length"],
            parent_resolution_id=submitted["parent_resolution_id"],
        )
        if current != submitted:
            raise ValidationError("The tie impact changed. Preview it again.")
        resolution = TieResolution.objects.create(
            draw=group.draw,
            group=group,
            parent_id=current["parent_resolution_id"],
            method=current["method"],
            state=TieResolution.State.CONFIRMED
            if current["method"] == TieResolution.Method.MANUAL
            else TieResolution.State.PENDING,
            source_fingerprint=current["source_fingerprint"],
            places=current["places"],
            decision_order=current["ordered_entry_ids"],
        )
        resolution.contenders.set(current["tied_entry_ids"])
        if resolution.method == TieResolution.Method.EXTRA_MATCHES:
            _save_group_rounds(
                group,
                current["tied_entry_ids"],
                meetings=1,
                resolution=resolution,
                series_length=current["series_length"],
            )
        update_round_robin_completion(group.draw)
        names = dict(group.entries.values_list("pk", "entrant__display_name"))
        _record_change(
            competition,
            actor=actor,
            kind="group_tie_confirmed",
            internal_reason=internal_reason,
            private_data=current,
            public_data={
                "kind": "group_tie_confirmed",
                "group_id": group.pk,
                "group_name": group.name,
                "resolution_id": resolution.pk,
                "method": resolution.method,
                "places": resolution.places,
                "tied_entries": [names[pk] for pk in current["tied_entry_ids"]],
                "ordered_entries": [names[pk] for pk in current["ordered_entry_ids"]],
            },
        )
        resolution.refresh_from_db()
        return resolution


def _standing_snapshot(state):
    return {
        "standings": [
            {**asdict(row), "points": str(row.points)} for row in state["standings"]
        ],
        "qualifiers": state["qualifiers"],
        "qualification_state": state["qualification_state"],
    }


def project_group_correction(
    match, *, outcome, side_one_score, side_two_score, winner_entry_id
):
    group = match.round.group
    before = group_standings(group)
    after = group_standings(
        group,
        replacement=(
            match.pk,
            {
                "outcome": outcome,
                "side_one_score": side_one_score,
                "side_two_score": side_two_score,
                "winner_id": winner_entry_id,
            },
        ),
    )
    active = list(
        group.tie_resolutions.exclude(state=TieResolution.State.SUPERSEDED).values_list(
            "pk", flat=True
        )
    )
    invalid = [pk for pk in active if pk not in after["resolution_states"]]
    historical = (
        Match.objects.filter(round__tie_resolution_id__in=invalid)
        .select_related("winner__entrant")
        .prefetch_related("slots__resolved_entry__entrant")
    )
    return {
        "group_id": group.pk,
        "group_name": group.name,
        "before": _standing_snapshot(before),
        "after": _standing_snapshot(after),
        "invalidated_resolution_ids": invalid,
        "revalidated_resolution_ids": [pk for pk in active if pk not in invalid],
        "historical_matches": [_match_snapshot(m) for m in historical],
    }


def apply_group_correction_impact(match, impact):
    TieResolution.objects.filter(pk__in=impact["invalidated_resolution_ids"]).update(
        state=TieResolution.State.SUPERSEDED
    )


def _points(win_points, draw_points, loss_points):
    try:
        values = tuple(
            Decimal(str(value)) for value in (win_points, draw_points, loss_points)
        )
        if any(
            not value.is_finite()
            or value < 0
            or value >= Decimal("100000000")
            or value != value.quantize(Decimal(".01"))
            for value in values
        ):
            raise ValueError
        if not values[0] > values[1] >= values[2]:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValidationError(
            "Use nonnegative points with two decimal places and win > draw >= loss."
        ) from error
    return values


def _rules(meetings, series_mode, length, points, tiebreaks):
    if type(meetings) is not int or meetings not in (1, 2):
        raise ValidationError("Choose one or two meetings per pair.")
    _validate_series_length(series_mode, length)
    _points(*points)
    if (
        not isinstance(tiebreaks, (list, tuple))
        or any(not isinstance(rule, str) or rule not in TIEBREAKS for rule in tiebreaks)
        or len(tiebreaks) != len(set(tiebreaks))
    ):
        raise ValidationError("Choose each supported tiebreaker at most once.")


def configure_round_robin(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    name: str,
    meetings: int,
    series_mode: str,
    default_series_length: int,
    win_points: Decimal,
    draw_points: Decimal,
    loss_points: Decimal,
    tiebreaks: Sequence[str] = DEFAULT_TIEBREAKS,
    stage_sequence: int = 1,
) -> Stage:
    require_organizer(actor, "competitions.change_competition")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValidationError({"name": "Enter a stage name of at most 100 characters."})
    points = _points(win_points, draw_points, loss_points)
    _rules(meetings, series_mode, default_series_length, points, tiebreaks)
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        _validate_stage_sequence(competition, stage_sequence)
        stage = (
            Stage.objects.select_for_update()
            .filter(competition=competition, sequence=stage_sequence)
            .first()
        )
        if stage and stage.published_at:
            raise ValidationError("Published stage setup is locked.")
        if stage:
            stage.draws.filter(state=StageDraw.State.DRAFT).update(
                state=StageDraw.State.SUPERSEDED
            )
        values = {
            "name": name.strip(),
            "advancement_count": None,
            "format": Stage.Format.ROUND_ROBIN,
            "grand_final_policy": "",
            "series_mode": series_mode,
            "default_series_length": default_series_length,
            "round_robin_meetings": meetings,
            "win_points": points[0],
            "draw_points": points[1],
            "loss_points": points[2],
            "tiebreaks": list(tiebreaks),
        }
        if stage:
            for key, value in values.items():
                setattr(stage, key, value)
            stage.save(update_fields=tuple(values))
        else:
            stage = Stage.objects.create(
                competition=competition, sequence=stage_sequence, **values
            )
        _record_change(
            competition,
            actor=actor,
            kind="stage_configured",
            private_data={
                "stage_id": stage.pk,
                **values,
                "win_points": str(points[0]),
                "draw_points": str(points[1]),
                "loss_points": str(points[2]),
            },
        )
        return stage


def _save_group_rounds(
    group, entry_ids, *, meetings, resolution=None, series_length=None
):
    generated = generate_round_robin(entry_ids, meetings=meetings)
    section = Round.Section.TIEBREAK if resolution else Round.Section.NORMAL
    offset = (
        (
            group.rounds.filter(section=section)
            .order_by("-number")
            .values_list("number", flat=True)
            .first()
            or 0
        )
        if resolution
        else 0
    )
    ordinal = Match.objects.filter(round__draw=group.draw).count()
    for fixture in generated:
        round_ = Round.objects.create(
            draw=group.draw,
            group=group,
            number=offset + fixture.number,
            section=section,
            tie_resolution=resolution,
            series_mode_override=Stage.SeriesMode.BEST_OF if resolution else "",
            series_length_override=series_length,
        )
        matches = Match.objects.bulk_create(
            [
                Match(
                    round=round_,
                    number=number,
                    code=f"{group.draw.stage.name}-M{ordinal + number}",
                )
                for number, _ in enumerate(fixture.pairings, 1)
            ]
        )
        ordinal += len(matches)
        MatchSlot.objects.bulk_create(
            [
                MatchSlot(
                    match=match,
                    position=position,
                    entry_id=entry_id,
                    resolved_entry_id=entry_id,
                    is_resolved=True,
                )
                for match, pairing in zip(matches, fixture.pairings, strict=True)
                for position, entry_id in enumerate(pairing, 1)
            ]
        )


def save_round_robin_draw(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    group_specs: Sequence[tuple[str, int]],
    ordered_entrant_ids: Sequence[int],
    memberships: Sequence[Sequence[int]] | None = None,
    randomize: bool = False,
    stage_id: int | None = None,
) -> StageDraw:
    require_organizer(actor, "competitions.change_competition")
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = _stage_for_command(competition, stage_id)
        if stage.sequence != 1:
            raise ValidationError(
                "Generate later draws from the previous stage qualifiers."
            )
        if not stage or stage.format != Stage.Format.ROUND_ROBIN:
            raise ValidationError("Configure round robin before saving groups.")
        if stage.published_at:
            raise ValidationError("The published draw cannot be replaced directly.")
        entrants = list(
            competition.entrants.select_for_update().filter(
                is_selected=True, status=CompetitionEntrant.Status.ACTIVE
            )
        )
        ids = list(ordered_entrant_ids)
        if (
            not 2 <= len(entrants) <= MAX_ENTRANTS
            or len(ids) != len(set(ids))
            or set(ids) != {row.pk for row in entrants}
        ):
            raise ValidationError("Include every selected entrant exactly once.")
        if randomize:
            if memberships is not None:
                raise ValidationError("Random ordering requires snake allocation.")
            secrets.SystemRandom().shuffle(ids)
        try:
            specs = [(name.strip(), places) for name, places in group_specs]
            if not specs or any(
                not 1 <= len(name) <= 100 or type(places) is not int or places < 1
                for name, places in specs
            ):
                raise ValueError
            if len({name for name, _ in specs}) != len(specs):
                raise ValueError
            allocations = (
                list(memberships)
                if memberships is not None
                else allocate_snake_groups(ids, len(specs))
            )
            if len(allocations) != len(specs):
                raise ValueError
            flattened = [entry for group in allocations for entry in group]
            if len(flattened) != len(ids) or set(flattened) != set(ids):
                raise ValueError
            if any(
                len(group) < 2 or places > len(group)
                for group, (_, places) in zip(allocations, specs, strict=True)
            ):
                raise ValueError
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError(
                "Use unique named groups of at least two entrants and valid qualifying places; allocate every entrant once."
            ) from error
        if (
            sum(
                len(group) * (len(group) - 1) // 2 * stage.round_robin_meetings
                for group in allocations
            )
            > MAX_MATCHES
        ):
            raise ValidationError("The generated draw exceeds the match limit.")
        planned = [
            (p.name, p.size, p.qualifying_places) for p in stage.group_plans.all()
        ]
        actual = [
            (name, len(group), quota)
            for (name, quota), group in zip(specs, allocations, strict=True)
        ]
        if planned and actual != planned:
            raise ValidationError(
                "Saved group membership must match the configured group plan."
            )
        if not planned:
            StageGroupPlan.objects.bulk_create(
                [
                    StageGroupPlan(
                        stage=stage,
                        number=i,
                        name=name,
                        size=size,
                        qualifying_places=quota,
                    )
                    for i, (name, size, quota) in enumerate(actual, 1)
                ]
            )
        stage.draws.filter(state=StageDraw.State.DRAFT).update(
            state=StageDraw.State.SUPERSEDED
        )
        version = (
            stage.draws.order_by("-version").values_list("version", flat=True).first()
            or 0
        ) + 1
        draw = StageDraw.objects.create(
            stage=stage, version=version, randomized=randomize
        )
        groups = [
            StageGroup.objects.create(
                draw=draw, number=number, name=name, qualifying_places=places
            )
            for number, (name, places) in enumerate(specs, 1)
        ]
        group_by_entrant = {
            entrant: group
            for group, allocation in zip(groups, allocations, strict=True)
            for entrant in allocation
        }
        entries = StageEntry.objects.bulk_create(
            [
                StageEntry(
                    draw=draw,
                    entrant_id=entrant,
                    group=group_by_entrant[entrant],
                    seed=seed,
                )
                for seed, entrant in enumerate(ids, 1)
            ]
        )
        for group in groups:
            _save_group_rounds(
                group,
                [entry.pk for entry in entries if entry.group_id == group.pk],
                meetings=stage.round_robin_meetings,
            )
        _record_change(
            competition,
            actor=actor,
            kind="draw_saved",
            private_data={
                "draw_id": draw.pk,
                "entrant_order": ids,
                "randomized": randomize,
            },
        )
        return draw


def validate_round_robin_draw(draw):
    stage = draw.stage
    _rules(
        stage.round_robin_meetings,
        stage.series_mode,
        stage.default_series_length,
        (stage.win_points, stage.draw_points, stage.loss_points),
        stage.tiebreaks,
    )
    groups = list(draw.groups.all())
    if (
        not groups
        or draw.entries.filter(group__isnull=True).exists()
        or draw.entries.exclude(group__draw=draw).exists()
    ):
        raise ValidationError("Every entrant needs a group in this draw.")
    expected_rounds = set()
    for group in groups:
        entries = list(group.entries.order_by("seed").values_list("pk", flat=True))
        if len(entries) < 2 or not 1 <= group.qualifying_places <= len(entries):
            raise ValidationError(
                "Every group needs at least two entrants and valid qualifying places."
            )
        for fixture in generate_round_robin(
            entries, meetings=stage.round_robin_meetings
        ):
            expected_rounds.add((group.pk, fixture.number))
            round_ = draw.rounds.filter(
                group=group, number=fixture.number, section=Round.Section.NORMAL
            ).first()
            if (
                round_ is None
                or round_.tie_resolution_id
                or round_.series_mode_override
            ):
                raise ValidationError("The saved group schedule is incomplete.")
            matches = list(round_.matches.order_by("number").prefetch_related("slots"))
            if [match.number for match in matches] != list(
                range(1, len(fixture.pairings) + 1)
            ):
                raise ValidationError(
                    "The saved group schedule has incorrect meetings."
                )
            for match, pairing in zip(matches, fixture.pairings, strict=True):
                slots = list(match.slots.all())
                if len(slots) != 2 or any(
                    slot.position != position
                    or slot.entry_id != entry_id
                    or slot.resolved_entry_id != entry_id
                    or not slot.is_resolved
                    or slot.source_match_id
                    or slot.is_empty
                    or slot.source_outcome
                    for position, (slot, entry_id) in enumerate(
                        zip(slots, pairing, strict=True), 1
                    )
                ):
                    raise ValidationError(
                        "The saved group fixtures do not match membership."
                    )
    if set(draw.rounds.values_list("group_id", "number")) != expected_rounds:
        raise ValidationError("The saved draw has extra or missing rounds.")
