"""Exact qualified fields, saved random draws, and cross-stage validity."""

import secrets

from django.core.exceptions import ValidationError
from django.db import transaction

from config.organizers import require_organizer
from registrations.models import Registration
from .command_support import (
    _check_revision,
    _lock_competition,
    _persist_stage_draw,
    _record_change,
    _stage_for_command,
)
from .models import CompetitionEntrant, Stage
from .qualification import stage_qualification


def _source_field(stage):
    previous = stage.competition.stages.filter(sequence=stage.sequence - 1).first()
    source = previous.draws.filter(state="PUBLISHED").first() if previous else None
    if source is None:
        raise ValidationError(
            "The immediately preceding stage needs a current published draw."
        )
    snapshot = stage_qualification(source)
    if snapshot["qualification_state"] != "RESOLVED":
        raise ValidationError(
            snapshot["block_reason"]
            or "Finish all required previous-stage matches and resolve every qualification cutoff."
        )
    entries = list(
        source.entries.filter(pk__in=snapshot["qualifier_entry_ids"])
        .select_related("entrant__registration")
        .order_by("pk")
    )
    expected = (
        sum(p.qualifying_places for p in previous.group_plans.all())
        if previous.format == Stage.Format.ROUND_ROBIN
        else previous.advancement_count
    )
    if (
        len(entries) != len(snapshot["qualifier_entry_ids"])
        or expected is not None
        and len(entries) != expected
    ):
        raise ValidationError(
            "The qualified field does not fit the locked destination plan."
        )
    from .stage_commands import validate_stage_field

    validate_stage_field(stage, len(entries))
    registrations = list(
        Registration.objects.select_for_update()
        .filter(pk__in=[e.entrant.registration_id for e in entries])
        .order_by("pk")
    )
    if (
        len(registrations) != len(entries)
        or any(
            r.status != "APPROVED"
            or r.tournament_game_id != stage.competition.tournament_game_id
            for r in registrations
        )
        or any(
            e.entrant.status != CompetitionEntrant.Status.ACTIVE
            or e.entrant.competition_id != stage.competition_id
            for e in entries
        )
    ):
        raise ValidationError(
            "Every qualifier must still be active and approved for this division; substitutions are not allowed."
        )
    return source, snapshot, entries


def validate_draw_source(draw):
    stage = draw.stage
    source, snapshot, entries = _source_field(stage)
    saved = list(draw.entries.select_related("source_entry"))
    if (
        draw.source_draw_id != source.pk
        or draw.source_fingerprint != snapshot["fingerprint"]
        or len(saved) != len(entries)
        or {e.source_entry_id for e in saved} != {e.pk for e in entries}
        or any(
            e.source_entry is None
            or e.source_entry.entrant_id != e.entrant_id
            or e.source_entry.draw_id != source.pk
            for e in saved
        )
    ):
        raise ValidationError(
            "The saved draw's source or qualifier membership changed. Generate a valid replacement draw."
        )
    return snapshot


def generate_next_stage_draw(
    *, actor, stage_id: int, expected_revision: int, regenerate: bool = False
):
    require_organizer(actor, "competitions.change_competition")
    competition_id = Stage.objects.values_list("competition_id", flat=True).get(
        pk=stage_id
    )
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = _stage_for_command(competition, stage_id)
        if stage.sequence <= 1:
            raise ValidationError("Only later stages use qualified successor draws.")
        if stage.draws.filter(state="PUBLISHED").exists():
            raise ValidationError("A published draw cannot be regenerated directly.")
        source, snapshot, entries = _source_field(stage)
        current = stage.draws.filter(state="DRAFT").first()
        if current and not regenerate:
            validate_draw_source(current)
            if stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
                from .swiss_commands import validate_swiss_round

                validate_swiss_round(
                    current.rounds.get(state="DRAFT"), verify_pairing=False
                )
            return current
        order = [e.entrant_id for e in entries]
        secrets.SystemRandom().shuffle(order)
        plans = list(stage.group_plans.all())
        from .stage_commands import resolve_group_sizes

        sizes = (
            resolve_group_sizes(
                [(p.name, p.size, p.qualifying_places) for p in plans], len(order)
            )
            if plans
            else []
        )
        allocations = []
        offset = 0
        for size in sizes:
            allocations.append(order[offset : offset + size])
            offset += size
        draw = _persist_stage_draw(
            stage,
            order,
            randomized=True,
            source_draw=source,
            source_fingerprint=snapshot["fingerprint"],
            source_entries={e.entrant_id: e.pk for e in entries},
            group_specs=[(p.name, p.qualifying_places) for p in plans],
            allocations=allocations,
        )
        private_data = {
            "stage_id": stage.pk,
            "draw_id": draw.pk,
            "source_draw_id": source.pk,
            "source_fingerprint": snapshot["fingerprint"],
            "entrant_order": order,
            "regenerated": regenerate,
        }
        if stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
            from .swiss_commands import _swiss_round_payload

            private_data["swiss_round"] = _swiss_round_payload(draw.rounds.get())
        _record_change(
            competition,
            actor=actor,
            kind="successor_draw_saved",
            private_data=private_data,
        )
        return draw


def project_handoff_corrections(
    source_draw, *, projected_qualification, source_needs_replay
):
    from .command_support import _match_snapshot
    from .models import Match, StageDraw

    impact = {
        "retained_draw_ids": [],
        "superseded_draw_ids": [],
        "reset_matches": [],
        "retained_draws": [],
        "retired_draws": [],
    }
    current_source = source_draw
    snapshot = projected_qualification
    retire = source_needs_replay or any(
        snapshot["resolution_states"].get(resolution.pk) != resolution.state
        for resolution in source_draw.tie_resolutions.exclude(state="SUPERSEDED")
    )
    draws = (
        StageDraw.objects.filter(
            stage__competition=source_draw.stage.competition,
            stage__sequence__gt=source_draw.stage.sequence,
        )
        .exclude(state="SUPERSEDED")
        .select_related("stage")
        .order_by("stage__sequence")
    )
    for draw in draws:
        entries = list(draw.entries.select_related("entrant__registration"))
        valid = (
            not retire
            and snapshot["qualification_state"] == "RESOLVED"
            and draw.source_draw_id == current_source.pk
            and {e.source_entry_id for e in entries}
            == set(snapshot["qualifier_entry_ids"])
            and all(
                e.entrant.status == "ACTIVE"
                and e.entrant.registration.status == "APPROVED"
                and e.entrant.registration.tournament_game_id
                == source_draw.stage.competition.tournament_game_id
                for e in entries
            )
        )
        if valid:
            impact["retained_draw_ids"].append(draw.pk)
            impact["retained_draws"].append(
                {"draw_id": draw.pk, "source_fingerprint": snapshot["fingerprint"]}
            )
            current_source = draw
            snapshot = stage_qualification(draw)
        else:
            retire = True
            impact["superseded_draw_ids"].append(draw.pk)
            impact["retired_draws"].append(
                {
                    "draw_id": draw.pk,
                    "stage_id": draw.stage_id,
                    "was_published": draw.published_at is not None,
                }
            )
            for match in (
                Match.objects.filter(round__draw=draw, status__in=("LIVE", "FINAL"))
                .exclude(outcome__in=("BYE", "EMPTY"))
                .select_related("winner__entrant")
                .prefetch_related("slots__resolved_entry__entrant")
                .order_by("pk")
            ):
                impact["reset_matches"].append(
                    {
                        **_match_snapshot(match),
                        "draw_id": draw.pk,
                        "stage_id": draw.stage_id,
                        "was_published": draw.published_at is not None,
                    }
                )
    return impact


def apply_handoff_impact(impact):
    from .models import StageDraw, Stage

    for retained in impact["retained_draws"]:
        StageDraw.objects.filter(pk=retained["draw_id"]).update(
            source_fingerprint=retained["source_fingerprint"]
        )
    from .command_support import _supersede_draws

    _supersede_draws(StageDraw.objects.filter(pk__in=impact["superseded_draw_ids"]))
    for retired in impact["retired_draws"]:
        Stage.objects.filter(pk=retired["stage_id"]).update(
            status="AWAITING" if retired["was_published"] else "DRAFT",
            champion=None,
            completed_at=None,
            completed_without_champion=False,
        )


def public_handoff_impact(impact):
    return {
        "retired_draws": [
            {"stage_id": d["stage_id"], "draw_id": d["draw_id"]}
            for d in impact["retired_draws"]
            if d["was_published"]
        ],
        "reset_matches": [
            {k: v for k, v in m.items() if k != "was_published"}
            for m in impact["reset_matches"]
            if m["was_published"]
        ],
    }
