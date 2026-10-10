"""Draw-scoped qualification and the shared explicit cutoff decisions."""

import hashlib
import json
from copy import copy
from dataclasses import asdict
from decimal import Decimal
from itertools import groupby

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from config.organizers import require_organizer
from .command_support import (
    MAX_MATCHES,
    _check_revision,
    _lock_competition,
    _record_change,
    _validate_series_length,
)
from .elimination import EliminationResult, finishing_bands
from .models import Match, Round, Stage, StageDraw, StageGroup, TieResolution
from .round_robin import generate_round_robin, rank_group

TIE_SALT = "competitions.group_tie"


def select_qualifiers(rows, cutoff, fingerprint, *, resolutions, matches, results_for):
    from .round_robin_commands import _fingerprint

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

    qualifiers = select(rows, cutoff, fingerprint)
    return qualifiers, ties, states


def projected_fixture_matches(draw, projected_matches=None):
    matches = getattr(draw, "_qualification_matches", None)
    if matches is None:
        matches = list(
            Match.objects.filter(round__draw=draw)
            .select_related("round")
            .prefetch_related("slots")
        )
    matches = [m for m in matches if m.round.state == Round.State.PUBLISHED]
    if not projected_matches:
        return matches
    projected = []
    for match in matches:
        values = projected_matches.get(match.pk)
        if values:
            match = copy(match)
            for key in (
                "status",
                "outcome",
                "side_one_score",
                "side_two_score",
                "winner_id",
            ):
                if key in values:
                    setattr(match, key, values[key])
            if "slots" in values:
                slots = [copy(slot) for slot in match.slots.all()]
                for slot, (resolved, entry_id) in zip(
                    slots, values["slots"], strict=True
                ):
                    slot.is_resolved = resolved
                    slot.resolved_entry_id = entry_id
                match._prefetched_objects_cache = {"slots": slots}
        projected.append(match)
    return projected


def stage_qualification(draw, *, projected_matches=None):
    from .round_robin_commands import _results, group_standings

    stage = draw.stage
    matches = projected_fixture_matches(draw, projected_matches)
    ordinary = [m for m in matches if m.round.section != Round.Section.TIEBREAK]
    complete = bool(ordinary) and all(
        m.status in ("FINAL", "NOT_REQUIRED") for m in ordinary
    )
    cutoffs = []
    qualifiers = []
    bands = []
    states = {}
    blocked = None
    inputs = []
    if stage.format == Stage.Format.ROUND_ROBIN:
        group_states = []
        for group in draw.groups.all():
            group._standings_matches = [
                m for m in matches if m.round.group_id == group.pk
            ]
            state = group_standings(group)
            group_states.append(state["qualification_state"])
            qualifiers.extend(state["qualifiers"])
            states.update(state["resolution_states"])
            cutoffs.extend(
                {"group_id": group.pk, **tie} for tie in state["cutoff_ties"]
            )
            inputs.append([group.pk, group.qualifying_places, state["fingerprint"]])
        complete = complete and bool(group_states) and "PROVISIONAL" not in group_states
    elif stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
        from .swiss_commands import _swiss_source_fingerprint, swiss_standings

        rounds = list(
            draw.rounds.filter(
                state=Round.State.PUBLISHED, section=Round.Section.NORMAL
            ).order_by("number")
        )
        rows = swiss_standings(draw, projected_matches=matches)
        source = _swiss_source_fingerprint(
            draw, (draw.swiss_round_limit or 0) + 1, projected_matches=matches
        )
        extra = [m for m in matches if m.round.section == Round.Section.TIEBREAK]
        inputs = [
            source,
            [[r.pk, r.number, r.version] for r in rounds],
            [[m.pk, m.status] for m in ordinary],
            [asdict(r) for r in _results(extra)],
        ]
        bands = [
            [row.entry_id for row in band]
            for _, band in groupby(rows, key=lambda row: row.rank)
        ]
        if stage.format == Stage.Format.SWISS_FIXED:
            complete = complete and [r.number for r in rounds] == list(
                range(1, (draw.swiss_round_limit or 0) + 1)
            )
            if complete:
                resolutions = list(
                    draw.tie_resolutions.filter(group__isnull=True).prefetch_related(
                        "contenders"
                    )
                )
                qualifiers, ties, states = select_qualifiers(
                    rows,
                    stage.advancement_count,
                    source,
                    resolutions=resolutions,
                    matches=matches,
                    results_for=_results,
                )
                cutoffs = [{"group_id": None, **tie} for tie in ties]
        else:
            complete = complete and not any(row.status == "ACTIVE" for row in rows)
            if complete:
                qualifiers = [row.entry_id for row in rows if row.status == "QUALIFIED"]
    else:
        entry_ids = [e.pk for e in draw.entries.all()]
        results = []
        for match in ordinary:
            slots = list(match.slots.all())
            results.append(
                EliminationResult(
                    match.round.number,
                    match.round.section,
                    match.status,
                    match.outcome,
                    slots[0].resolved_entry_id,
                    slots[1].resolved_entry_id,
                    match.winner_id,
                )
            )
        inputs = [asdict(r) for r in results]
        source = hashlib.sha256(
            json.dumps([stage.advancement_count, inputs], sort_keys=True).encode()
        ).hexdigest()
        if complete:
            try:
                placement = finishing_bands(entry_ids, results, format=stage.format)
            except ValueError:
                blocked = "Terminal placement is inconsistent; resolve the recorded results before advancing."
            else:
                bands = [list(band) for band in placement.bands]
            quota = stage.advancement_count
            if quota is not None and blocked is None:
                if quota == len(entry_ids):
                    qualifiers = entry_ids
                elif sum(map(len, bands)) < quota:
                    blocked = "Terminal placement is undefined after an upper-bracket double forfeit; the configured cutoff cannot be determined."
                else:
                    from types import SimpleNamespace

                    rows = []
                    rank = 1
                    for band in bands:
                        rows.extend(
                            SimpleNamespace(entry_id=i, rank=rank) for i in band
                        )
                        rank += len(band)
                    resolutions = list(
                        draw.tie_resolutions.filter(
                            group__isnull=True
                        ).prefetch_related("contenders")
                    )
                    qualifiers, ties, states = select_qualifiers(
                        rows,
                        quota,
                        source,
                        resolutions=resolutions,
                        matches=matches,
                        results_for=_results,
                    )
                    cutoffs = [{"group_id": None, **tie} for tie in ties]
    decisions = []
    for resolution in draw.tie_resolutions.all():
        if resolution.pk in states:
            decisions.append(
                [
                    resolution.pk,
                    resolution.source_fingerprint,
                    states[resolution.pk],
                    resolution.decision_order,
                ]
            )
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                stage.format,
                stage.advancement_count,
                inputs,
                decisions,
                sorted(qualifiers),
                cutoffs,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "qualification_state": "PROVISIONAL"
        if not complete
        else "BLOCKED"
        if blocked
        else "AWAITING_RESOLUTION"
        if cutoffs
        else "RESOLVED",
        "qualifier_entry_ids": qualifiers if complete else [],
        "fingerprint": fingerprint,
        "block_reason": blocked,
        "bands": bands,
        "cutoffs": cutoffs,
        "resolution_states": states,
    }


def _tie_payload(
    draw,
    group=None,
    *,
    expected_revision,
    tied_entry_ids,
    method,
    ordered_entry_ids=(),
    series_length=1,
    parent_resolution_id=None,
):
    _check_revision(draw.stage.competition, expected_revision)
    if draw.state != StageDraw.State.PUBLISHED:
        raise ValidationError("Only current published draws can resolve a cutoff.")
    if draw.stage.format == Stage.Format.ROUND_ROBIN:
        if group is None or group.draw_id != draw.pk:
            raise ValidationError("Choose a group belonging to this draw.")
    elif group is not None:
        raise ValidationError("Draw cutoff decisions have no group scope.")
    state = stage_qualification(draw)
    tie = next(
        (
            tie
            for tie in state["cutoffs"]
            if tie["group_id"] == (group.pk if group else None)
            and set(tie["entry_ids"]) == set(tied_entry_ids)
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
            round__draw=draw, round__section=Round.Section.TIEBREAK
        ).count()
        if existing + count > MAX_MATCHES:
            raise ValidationError(
                "The extra-match budget is exhausted. Use an organizer decision."
            )
    return {
        "draw_id": draw.pk,
        "group_id": group.pk if group else None,
        "competition_id": draw.stage.competition_id,
        "revision": expected_revision,
        "tied_entry_ids": tie["entry_ids"],
        "places": tie["places"],
        "source_fingerprint": tie["source_fingerprint"],
        "method": method,
        "ordered_entry_ids": list(ordered_entry_ids),
        "series_length": series_length,
        "parent_resolution_id": parent_resolution_id,
    }


def preview_qualification_tie(
    *,
    actor,
    draw_id,
    group_id=None,
    expected_revision,
    tied_entry_ids,
    method,
    ordered_entry_ids=(),
    series_length=1,
    parent_resolution_id=None,
):
    require_organizer(actor, "competitions.change_competition")
    draw = StageDraw.objects.select_related("stage__competition").get(pk=draw_id)
    group = (
        StageGroup.objects.filter(pk=group_id, draw=draw).first()
        if group_id is not None
        else None
    )
    if group_id is not None and group is None:
        raise ValidationError("Choose a group belonging to this draw.")
    payload = _tie_payload(
        draw,
        group=group,
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


def confirm_qualification_tie(*, actor, token, internal_reason=""):
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
        draw = (
            StageDraw.objects.select_for_update()
            .select_related("stage")
            .get(pk=submitted["draw_id"], stage__competition=competition)
        )
        draw.stage.competition = competition
        group = (
            StageGroup.objects.filter(pk=submitted["group_id"], draw=draw).first()
            if submitted["group_id"] is not None
            else None
        )
        current = _tie_payload(
            draw,
            group=group,
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
            draw=draw,
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
            from .round_robin_commands import _save_group_rounds

            _save_group_rounds(
                group,
                current["tied_entry_ids"],
                draw=draw,
                meetings=1,
                resolution=resolution,
                series_length=current["series_length"],
            )
            resolution.rounds.filter(state=Round.State.DRAFT).update(
                state=Round.State.PUBLISHED, published_at=timezone.now()
            )
        from .commands import _update_stage_completion

        _update_stage_completion(draw)
        names = dict(draw.entries.values_list("pk", "entrant__display_name"))
        kind = "group_tie_confirmed" if group else "qualification_tie_confirmed"
        _record_change(
            competition,
            actor=actor,
            kind=kind,
            internal_reason=internal_reason,
            private_data=current,
            public_data={
                "kind": kind,
                "stage_id": draw.stage_id,
                "group_id": group.pk if group else None,
                "group_name": group.name if group else None,
                "resolution_id": resolution.pk,
                "method": resolution.method,
                "places": resolution.places,
                "tied_entries": [names[pk] for pk in current["tied_entry_ids"]],
                "ordered_entries": [names[pk] for pk in current["ordered_entry_ids"]],
            },
        )
        resolution.refresh_from_db()
        return resolution
