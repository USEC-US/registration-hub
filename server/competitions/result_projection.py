"""Shared elimination simulation; callers own locks, consent, history and provenance."""

from graphlib import CycleError, TopologicalSorter

from django.core.exceptions import ValidationError
from django.utils import timezone

from .command_support import _match_snapshot
from .models import CompetitionEntrant, Match, MatchSlot, Round, Stage, StageDraw


def _ordered_matches(draw: StageDraw, *, include_drafts=False) -> list[Match]:
    queryset = Match.objects.filter(round__draw=draw).exclude(
        round__state=Round.State.SUPERSEDED
    )
    if not include_drafts:
        queryset = queryset.filter(round__state=Round.State.PUBLISHED)
    matches = list(
        queryset.select_related("round__draw__stage").order_by(
            "round__section", "round__number", "number", "pk"
        )
    )
    by_id = {match.pk: match for match in matches}
    graph = {match.pk: [] for match in matches}
    for match_id, source_id in (
        MatchSlot.objects.filter(match_id__in=by_id, source_match__isnull=False)
        .order_by("match_id", "position")
        .values_list("match_id", "source_match_id")
    ):
        if source_id not in by_id:
            raise ValidationError("Match sources must belong to the same draw.")
        graph[match_id].append(source_id)
    try:
        return [by_id[pk] for pk in TopologicalSorter(graph).static_order()]
    except CycleError as error:
        raise ValidationError("Match sources cannot form a cycle.") from error


def _reset_final_status(
    *, first_status, first_outcome, winner_id, lower_entry_id, status
):
    if first_status != Match.Status.FINAL:
        return Match.Status.CONDITIONAL
    if (
        first_outcome in (Match.Outcome.PLAYED, Match.Outcome.FORFEIT)
        and winner_id == lower_entry_id
    ):
        return (
            status
            if status in (Match.Status.LIVE, Match.Status.FINAL)
            else Match.Status.PENDING
        )
    return Match.Status.NOT_REQUIRED


def _reset_activation(status):
    return (
        "ACTIVE"
        if status in (Match.Status.PENDING, Match.Status.LIVE, Match.Status.FINAL)
        else status
    )


def _automatic_result(status, slots):
    if status in (
        Match.Status.FINAL,
        Match.Status.CONDITIONAL,
        Match.Status.NOT_REQUIRED,
    ):
        return None
    if len(slots) != 2 or not all(resolved for resolved, _ in slots):
        return None
    entries = [entry_id for _, entry_id in slots if entry_id is not None]
    if len(entries) == 2:
        return None
    return (Match.Outcome.BYE, entries[0]) if entries else (Match.Outcome.EMPTY, None)


def _routed_entry_id(outcome, winner_id, entries, source_outcome):
    if source_outcome == MatchSlot.SourceOutcome.WINNER:
        return winner_id
    if outcome not in (Match.Outcome.PLAYED, Match.Outcome.FORFEIT) or not winner_id:
        return None
    return next((entry_id for entry_id in entries if entry_id != winner_id), None)


COMPETITIVE_FIELDS = (
    "status",
    "outcome",
    "winner_id",
    "side_one_score",
    "side_two_score",
    "applied_series_length",
    "applied_series_mode",
    "started_at",
    "completed_at",
)


def project_elimination_results(
    draw: StageDraw,
    *,
    result_updates: dict[int, dict],
    entrant_statuses: dict[int, str] | None = None,
) -> dict:
    """Simulate a draw; updates use model fields, overrides use CompetitionEntrant IDs.

    Entered finals stay historical unless explicit result updates change inputs.
    Callers own transactions, consent, revision, history and removal provenance.
    """
    if draw.stage.format not in (
        Stage.Format.SINGLE_ELIMINATION,
        Stage.Format.DOUBLE_ELIMINATION,
    ):
        raise ValidationError("Result projection requires an elimination draw.")
    ordered = _ordered_matches(
        draw, include_drafts=draw.state != StageDraw.State.PUBLISHED
    )
    by_id = {m.pk: m for m in ordered}
    if result_updates.keys() - by_id.keys():
        raise ValidationError("Result updates must belong to the current draw.")
    if any(set(update) - set(COMPETITIVE_FIELDS) for update in result_updates.values()):
        raise ValidationError("Unsupported competitive result field.")
    entries = list(draw.entries.select_related("entrant"))
    statuses = entrant_statuses or {}
    available = {
        e.pk
        for e in entries
        if statuses.get(e.entrant_id, e.entrant.status)
        == CompetitionEntrant.Status.ACTIVE
    }
    names = {e.pk: e.entrant.display_name for e in entries}
    slots_by_match = {m.pk: [] for m in ordered}
    for slot in MatchSlot.objects.filter(match_id__in=by_id).order_by("position"):
        slots_by_match[slot.match_id].append(slot)
    projected, corrected = {}, {}
    changed, impacts, resets, reset_changes = [], [], [], []
    first_final_id = next(
        (
            m.pk
            for m in ordered
            if m.round.section == Round.Section.FINALS and m.round.number == 1
        ),
        None,
    )
    for item in ordered:
        saved_slots = [
            [s.is_resolved, s.resolved_entry_id] for s in slots_by_match[item.pk]
        ]
        slots, raw_slots = [], []
        source_corrected = False
        for slot in slots_by_match[item.pk]:
            if slot.source_match_id:
                source = projected[slot.source_match_id]
                resolved = source["status"] == Match.Status.FINAL
                entry = (
                    _routed_entry_id(
                        source["outcome"],
                        source["winner_id"],
                        [e for _, e in source["slots"]],
                        slot.source_outcome,
                    )
                    if resolved
                    else None
                )
                source_corrected |= corrected[slot.source_match_id]
                raw_slots.append([resolved, entry])
                slots.append([resolved, entry if entry in available else None])
            else:
                raw_slots.append([slot.is_resolved, slot.resolved_entry_id])
                slots.append(raw_slots[-1])
        entered_final = item.status == Match.Status.FINAL and item.outcome not in (
            Match.Outcome.BYE,
            Match.Outcome.EMPTY,
        )
        if entered_final and not source_corrected:
            slots = saved_slots
        state = {field: getattr(item, field) for field in COMPETITIVE_FIELDS}
        changed_inputs = slots != saved_slots
        invalidated = changed_inputs and (source_corrected or not entered_final)
        preserve_progress = item.status == Match.Status.LIVE and not source_corrected
        cleared = invalidated and not preserve_progress
        if cleared:
            state.update(
                status=Match.Status.PENDING,
                outcome="",
                winner_id=None,
                side_one_score=None,
                side_two_score=None,
                applied_series_length=None,
                applied_series_mode="",
                started_at=None,
                completed_at=None,
            )
        if item.round.section == Round.Section.FINALS and item.round.number == 2:
            first = projected[first_final_id]
            status = _reset_final_status(
                first_status=first["status"],
                first_outcome=first["outcome"],
                winner_id=first["winner_id"],
                lower_entry_id=first["slots"][1][1],
                status=state["status"],
            )
            before, after = _reset_activation(item.status), _reset_activation(status)
            if before != after:
                cleared = True
                reset_changes.append(
                    {
                        "match_id": item.pk,
                        "match_code": item.code,
                        "before": before,
                        "after": after,
                    }
                )
                state.update(
                    outcome="",
                    winner_id=None,
                    side_one_score=None,
                    side_two_score=None,
                    applied_series_length=None,
                    applied_series_mode="",
                    started_at=None,
                    completed_at=None,
                )
            state["status"] = status
        if item.pk in result_updates:
            state.update(result_updates[item.pk])
        else:
            result = _automatic_result(state["status"], slots)
            if state["status"] not in (
                Match.Status.FINAL,
                Match.Status.CONDITIONAL,
                Match.Status.NOT_REQUIRED,
            ) and all(r for r, _ in raw_slots):
                real = [e for _, e in raw_slots if e is not None]
                active = [e for e in real if e in available]
                if len(real) == 2 and len(active) < 2:
                    result = (
                        (Match.Outcome.FORFEIT, active[0])
                        if active
                        else (Match.Outcome.DOUBLE_FORFEIT, None)
                    )
                elif real and not active:
                    result = (Match.Outcome.EMPTY, None)
            if result:
                state.update(
                    status=Match.Status.FINAL, outcome=result[0], winner_id=result[1]
                )
                if result[0] in (Match.Outcome.BYE, Match.Outcome.EMPTY):
                    state.update(side_one_score=None, side_two_score=None)
        state["slots"] = slots
        corrected[item.pk] = (
            item.pk in result_updates
            and (state["winner_id"], state["outcome"], state["status"])
            != (item.winner_id, item.outcome, item.status)
        ) or (source_corrected and changed_inputs)
        projected[item.pk] = state
        if changed_inputs or any(
            state[f] != getattr(item, f) for f in COMPETITIVE_FIELDS
        ):
            changed.append(item.pk)
            before = _match_snapshot(item)
            after = {
                **before,
                **{
                    f: state[f]
                    for f in (
                        "status",
                        "outcome",
                        "side_one_score",
                        "side_two_score",
                        "applied_series_length",
                        "applied_series_mode",
                    )
                },
                "side_one": names.get(slots[0][1]),
                "side_two": names.get(slots[1][1]),
                "winner": names.get(state["winner_id"]),
                "started_at": state["started_at"].isoformat()
                if state["started_at"]
                else None,
                "completed_at": state["completed_at"].isoformat()
                if state["completed_at"]
                else None,
            }
            impacts.append(
                {
                    "match_id": item.pk,
                    "before": before,
                    "after": after,
                    "before_slots": saved_slots,
                    "after_slots": slots,
                    "after_status": state["status"],
                }
            )
            if (
                item.pk not in result_updates
                and item.status in (Match.Status.LIVE, Match.Status.FINAL)
                and item.outcome not in (Match.Outcome.BYE, Match.Outcome.EMPTY)
                and cleared
            ):
                resets.append(item.pk)
    return {
        "matches": projected,
        "changed_match_ids": sorted(changed),
        "match_impacts": impacts,
        "reset_match_ids": sorted(resets),
        "reset_final_changes": reset_changes,
    }


def apply_elimination_projection(draw: StageDraw, projection: dict) -> None:
    """Apply an authoritative projection inside the owning command's transaction."""
    current_ids = set(
        Match.objects.filter(round__draw=draw).values_list("pk", flat=True)
    )
    if set(projection["matches"]) - current_ids:
        raise ValidationError("Projected matches must belong to the draw.")
    now = timezone.now()
    for pk in projection["changed_match_ids"]:
        state = projection["matches"][pk]
        values = {f: state[f] for f in COMPETITIVE_FIELDS}
        if values["status"] == Match.Status.FINAL and values["completed_at"] is None:
            values["completed_at"] = now
        Match.objects.filter(pk=pk, round__draw=draw).update(**values)
        for position, (resolved, entry_id) in enumerate(state["slots"], 1):
            MatchSlot.objects.filter(match_id=pk, position=position).update(
                is_resolved=resolved, resolved_entry_id=entry_id
            )
