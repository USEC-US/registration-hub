"""Pure Swiss retirement projection and transaction-owned history retention."""

from collections.abc import Sequence

from .models import Match, Round, StageDraw
from .qualification import projected_fixture_matches, stage_qualification
from .swiss_commands import _swiss_source_fingerprint


def project_swiss_correction(
    draw: StageDraw,
    *,
    projected_matches: Sequence[Match] | None,
    entrant_statuses=None,
    retire_from_round=None,
) -> dict:
    """Project history retirement from a complete current published fixture sequence."""
    projected_matches = projected_fixture_matches(draw, projected_matches)
    rounds = list(
        draw.rounds.exclude(state=Round.State.SUPERSEDED).order_by("number", "pk")
    )
    changed = next(
        (
            round_.number
            for round_ in rounds
            if round_.section == Round.Section.NORMAL
            and round_.source_fingerprint
            != _swiss_source_fingerprint(
                draw,
                round_.number,
                projected_matches=projected_matches,
                availability_snapshot=round_.availability_snapshot
                if round_.state == Round.State.PUBLISHED
                else None,
                entrant_statuses=entrant_statuses,
            )
        ),
        None,
    )
    if retire_from_round is not None:
        changed = (
            min(changed, retire_from_round)
            if changed is not None
            else retire_from_round
        )
    retired = {
        r.pk
        for r in rounds
        if r.section == Round.Section.NORMAL
        and changed is not None
        and r.number >= changed
    }
    retained = [m for m in projected_matches if m.round_id not in retired]
    qualification = stage_qualification(
        draw, projected_matches=retained, entrant_statuses=entrant_statuses
    )
    invalidated_ties = (
        set(
            draw.tie_resolutions.exclude(state="SUPERSEDED").values_list(
                "pk", flat=True
            )
        )
        - qualification["resolution_states"].keys()
    )
    retired.update(r.pk for r in rounds if r.tie_resolution_id in invalidated_ties)
    matches = list(Match.objects.filter(round_id__in=retired).order_by("pk"))
    return {
        "retired_round_ids": [r.pk for r in rounds if r.pk in retired],
        "retired_match_ids": [m.pk for m in matches],
        "played_match_ids": [
            m.pk
            for m in matches
            if m.status in (Match.Status.LIVE, Match.Status.FINAL)
            and m.outcome not in (Match.Outcome.BYE, Match.Outcome.EMPTY)
        ],
        "current_match_ids": [
            m.pk for m in projected_matches if m.round_id not in retired
        ],
    }


def apply_swiss_correction(draw: StageDraw, impact: dict) -> None:
    Round.objects.filter(draw=draw, pk__in=impact["retired_round_ids"]).update(
        state=Round.State.SUPERSEDED
    )
