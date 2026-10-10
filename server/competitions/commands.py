from __future__ import annotations

import secrets
from collections.abc import Sequence
from graphlib import CycleError, TopologicalSorter

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from config.organizers import require_organizer
from registrations.models import Registration
from tournaments.models import TournamentGame

from .command_support import (
    MAX_ENTRANTS,
    MAX_MATCHES,
    _lock_competition,
    _check_revision,
    _record_change,
    _match_snapshot,
    _validate_best_of,
    _stage_for_command,
    _validate_stage_sequence,
    _validate_series_length,
    _persist_stage_draw,
    _supersede_draws,
    _supersede_ties,
)
from .elimination import (
    LoserSlot,
    SeedSlot,
    generate_double_elimination,
    generate_single_elimination,
)
from .models import (
    Competition,
    CompetitionEntrant,
    Match,
    MatchSlot,
    Round,
    Stage,
    StageDraw,
    StageEntry,
    TieResolution,
)

CORRECTION_SALT = "competitions.correction"


def create_competition(*, actor, tournament_game_id: int) -> Competition:
    require_organizer(actor, "competitions.add_competition")
    with transaction.atomic():
        division = TournamentGame.objects.select_for_update().get(pk=tournament_game_id)
        if Competition.objects.filter(tournament_game=division).exists():
            raise ValidationError("This division already has a competition.")
        competition = Competition.objects.create(tournament_game=division)
        _record_change(
            competition,
            actor=actor,
            kind="competition_created",
            private_data={"tournament_game_id": division.pk},
        )
        return competition


def configure_elimination(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    name: str,
    default_series_length: int,
    format: str,
    grand_final_policy: str = "",
    stage_sequence: int = 1,
) -> Stage:
    require_organizer(actor, "competitions.change_competition")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValidationError({"name": "Enter a stage name of at most 100 characters."})
    name = name.strip()
    _validate_elimination_setup(format, grand_final_policy)
    _validate_best_of(default_series_length)
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
        if stage is None:
            stage = Stage.objects.create(
                competition=competition,
                sequence=stage_sequence,
                name=name,
                format=format,
                grand_final_policy=grand_final_policy,
                series_mode=Stage.SeriesMode.BEST_OF,
                default_series_length=default_series_length,
            )
        else:
            if stage.format != format:
                stage.group_plans.all().delete()
            stage.swiss_round_count = None
            stage.swiss_win_target = None
            stage.swiss_loss_limit = None
            if stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
                stage.advancement_count = None
            stage.format = format
            stage.series_mode = Stage.SeriesMode.BEST_OF
            stage.grand_final_policy = grand_final_policy
            stage.name = name
            stage.default_series_length = default_series_length
            stage.save(
                update_fields=(
                    "name",
                    "default_series_length",
                    "format",
                    "series_mode",
                    "grand_final_policy",
                    "swiss_round_count",
                    "swiss_win_target",
                    "swiss_loss_limit",
                    "advancement_count",
                )
            )
        from .stage_commands import _invalidate_drafts

        _invalidate_drafts(stage)
        _record_change(
            competition,
            actor=actor,
            kind="stage_configured",
            private_data={
                "stage_id": stage.pk,
                "name": stage.name,
                "format": stage.format,
                "grand_final_policy": stage.grand_final_policy,
                "default_series_length": stage.default_series_length,
            },
        )
        return stage


def _entrant_label(registration: Registration) -> tuple[str, str]:
    if registration.tournament_game.is_individual:
        member = next(iter(registration.members.all()), None)
        if member is None:
            raise ValidationError(
                f"Registration {registration.pk} has no player snapshot."
            )
        return member.gamer_tag_snapshot, ""
    display_name = registration.team_name.strip() or registration.team_tag.strip()
    if not display_name:
        raise ValidationError(f"Registration {registration.pk} has no team label.")
    return display_name, registration.team_tag.strip()


def select_entrants(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    registration_ids: Sequence[int],
) -> list[CompetitionEntrant]:
    require_organizer(actor, "competitions.change_competition")
    unique_ids = list(dict.fromkeys(registration_ids))
    if len(unique_ids) != len(registration_ids):
        raise ValidationError("Choose each registration once.")
    if not 2 <= len(unique_ids) <= MAX_ENTRANTS:
        raise ValidationError(f"Choose between 2 and {MAX_ENTRANTS} entrants.")
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        if Stage.objects.filter(
            competition=competition, published_at__isnull=False
        ).exists():
            raise ValidationError("Published entrants cannot change directly.")
        registrations = list(
            Registration.objects.select_for_update()
            .filter(pk__in=unique_ids)
            .select_related("tournament_game")
            .prefetch_related("members")
            .order_by("pk")
        )
        if len(registrations) != len(unique_ids):
            raise ValidationError("One or more registrations no longer exist.")
        by_id = {registration.pk: registration for registration in registrations}
        for registration in registrations:
            if registration.tournament_game_id != competition.tournament_game_id:
                raise ValidationError("Every entrant must belong to this division.")
            if registration.status != Registration.Status.APPROVED:
                raise ValidationError("Only approved registrations can enter a draw.")
        _supersede_draws(
            StageDraw.objects.filter(
                stage__competition=competition, state=StageDraw.State.DRAFT
            )
        )
        first = competition.stages.filter(
            sequence=1, format=Stage.Format.ROUND_ROBIN
        ).first()
        if first:
            plans = list(first.group_plans.all())
            if (
                plans
                and all(p.size is not None for p in plans)
                and sum(p.size for p in plans) != len(unique_ids)
            ):
                first.group_plans.all().delete()
        competition.entrants.update(is_selected=False)
        entrants = []
        for registration_id in unique_ids:
            registration = by_id[registration_id]
            display_name, display_tag = _entrant_label(registration)
            entrants.append(
                CompetitionEntrant.objects.update_or_create(
                    competition=competition,
                    registration=registration,
                    defaults={
                        "display_name": display_name,
                        "display_tag": display_tag,
                        "is_selected": True,
                    },
                )[0]
            )
        _record_change(
            competition,
            actor=actor,
            kind="entrants_selected",
            private_data={"registration_ids": unique_ids},
        )
        return entrants


def save_elimination_draw(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    entrant_order: Sequence[int] | None = None,
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
                "Generate later draws from the previous stage's qualifiers."
            )
        if stage.published_at:
            raise ValidationError("The published draw cannot be replaced directly.")
        entrants = list(
            CompetitionEntrant.objects.select_for_update()
            .filter(
                competition=competition,
                is_selected=True,
                status=CompetitionEntrant.Status.ACTIVE,
            )
            .order_by("pk")
        )
        if not 2 <= len(entrants) <= MAX_ENTRANTS:
            raise ValidationError(f"Choose between 2 and {MAX_ENTRANTS} entrants.")
        entrant_ids = [entrant.pk for entrant in entrants]
        if randomize:
            ordered_ids = entrant_ids.copy()
            secrets.SystemRandom().shuffle(ordered_ids)
        else:
            ordered_ids = list(entrant_order or ())
            if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != set(
                entrant_ids
            ):
                raise ValidationError("Manual seeds must include every entrant once.")
        generated = _generate_elimination(stage, len(entrants))
        if sum(len(round_.matches) for round_ in generated) > MAX_MATCHES:
            raise ValidationError("The generated draw exceeds the match limit.")
        draw = _persist_stage_draw(stage, ordered_ids, randomized=randomize)
        _record_change(
            competition,
            actor=actor,
            kind="draw_saved",
            private_data={
                "draw_id": draw.pk,
                "entrant_order": ordered_ids,
                "randomized": randomize,
            },
        )
        return draw


def _persist_elimination_fixtures(draw, entries):
    stage = draw.stage
    generated = _generate_elimination(stage, len(entries))
    if sum(len(r.matches) for r in generated) > MAX_MATCHES:
        raise ValidationError("The generated draw exceeds the match limit.")
    entries_by_seed = {entry.seed: entry for entry in entries}
    matches: dict[tuple[str, int, int], Match] = {}
    for generated_round in generated:
        round_ = Round.objects.create(
            draw=draw,
            number=generated_round.number,
            section=generated_round.section,
        )
        for generated_match in generated_round.matches:
            match = Match.objects.create(
                round=round_,
                number=generated_match.number,
                code=f"{stage.name}-M{len(matches) + 1}",
                status=(
                    Match.Status.CONDITIONAL
                    if round_.section == Round.Section.FINALS and round_.number == 2
                    else Match.Status.PENDING
                ),
            )
            matches[(round_.section, round_.number, match.number)] = match
    # Persist the whole graph before linking either winner or loser routes.
    for generated_round in generated:
        for generated_match in generated_round.matches:
            match = matches[
                (
                    generated_round.section,
                    generated_round.number,
                    generated_match.number,
                )
            ]
            for position, slot in enumerate(generated_match.slots, start=1):
                if isinstance(slot, SeedSlot):
                    entry = entries_by_seed.get(slot.seed)
                    MatchSlot.objects.create(
                        match=match,
                        position=position,
                        entry=entry,
                        is_empty=entry is None,
                        is_resolved=True,
                        resolved_entry=entry,
                    )
                else:
                    MatchSlot.objects.create(
                        match=match,
                        position=position,
                        source_match=matches[
                            (slot.section, slot.round_number, slot.match_number)
                        ],
                        source_outcome=(
                            MatchSlot.SourceOutcome.LOSER
                            if isinstance(slot, LoserSlot)
                            else MatchSlot.SourceOutcome.WINNER
                        ),
                    )
    _resolve_automatic_matches(draw)


def publish_draw(
    *, actor, competition_id: int, expected_revision: int, stage_id: int | None = None
) -> StageDraw:
    require_organizer(actor, "competitions.change_competition")
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = _stage_for_command(competition, stage_id)
        from .stage_commands import _require_swiss_successor

        _require_swiss_successor(list(competition.stages.all()))
        if stage.draws.filter(state=StageDraw.State.PUBLISHED).exists():
            raise ValidationError("This stage is already published.")
        draw = (
            StageDraw.objects.select_for_update()
            .filter(stage=stage, state=StageDraw.State.DRAFT)
            .first()
        )
        if draw is None:
            raise ValidationError("Save a new draw before publication.")
        if stage.sequence > 1:
            from .handoff_commands import validate_draw_source

            validate_draw_source(draw)
            registration_ids = list(
                draw.entries.values_list("entrant__registration_id", flat=True)
            )
        else:
            registration_ids = list(
                competition.entrants.filter(is_selected=True)
                .order_by("registration_id")
                .values_list("registration_id", flat=True)
            )
            if set(
                draw.entries.values_list("entrant__registration_id", flat=True)
            ) != set(registration_ids):
                raise ValidationError(
                    "The draw does not contain every selected entrant."
                )
        registrations = list(
            Registration.objects.select_for_update()
            .filter(pk__in=registration_ids)
            .order_by("pk")
        )
        if len(registrations) != len(registration_ids) or any(
            registration.status != Registration.Status.APPROVED
            or registration.tournament_game_id != competition.tournament_game_id
            for registration in registrations
        ):
            raise ValidationError(
                "Every entrant must still be approved for this division."
            )
        if draw.entries.count() != len(registration_ids):
            raise ValidationError("The draw does not contain every selected entrant.")
        from .stage_commands import validate_stage_field

        validate_stage_field(stage, draw.entries.count())
        match_count = Match.objects.filter(round__draw=draw).count()
        slot_count = MatchSlot.objects.filter(match__round__draw=draw).count()
        if match_count == 0 or slot_count != match_count * 2:
            raise ValidationError("The saved draw is incomplete.")
        _validate_saved_draw(draw)
        from .stage_commands import validate_stage_plan

        if not competition.stages.filter(
            sequence=1, published_at__isnull=False
        ).exists():
            validate_stage_plan(competition)
        now = timezone.now()
        draw.state = StageDraw.State.PUBLISHED
        draw.published_at = now
        draw.save(update_fields=("state", "published_at"))
        draw.rounds.filter(state=Round.State.DRAFT).update(
            state=Round.State.PUBLISHED, published_at=now
        )
        stage.status = Stage.Status.READY
        stage.published_at = stage.published_at or now
        stage.save(update_fields=("status", "published_at"))
        swiss_public = {}
        if stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
            from .swiss_commands import _swiss_public_round

            _resolve_automatic_matches(draw)
            swiss_public = _swiss_public_round(
                draw.rounds.get(state=Round.State.PUBLISHED)
            )
        _record_change(
            competition,
            actor=actor,
            kind="draw_published",
            private_data={"draw_id": draw.pk},
            public_data={
                "kind": "draw_published",
                **swiss_public,
                "stage_id": stage.pk,
                "draw_id": draw.pk,
                "source_stage_id": draw.source_draw.stage_id
                if draw.source_draw_id
                else None,
            },
        )
        return draw


def _validate_elimination_setup(format: str, grand_final_policy: str) -> None:
    if format not in (Stage.Format.SINGLE_ELIMINATION, Stage.Format.DOUBLE_ELIMINATION):
        raise ValidationError("Choose a supported elimination format.")
    if format == Stage.Format.DOUBLE_ELIMINATION:
        if grand_final_policy not in Stage.GrandFinalPolicy.values:
            raise ValidationError({"grand_final_policy": "Choose reset or no reset."})
    elif grand_final_policy:
        raise ValidationError(
            {"grand_final_policy": "Single elimination has no final policy."}
        )


def _generate_elimination(stage: Stage, count: int):
    _validate_elimination_setup(stage.format, stage.grand_final_policy)
    if not 2 <= count <= MAX_ENTRANTS:
        raise ValidationError(f"Choose between 2 and {MAX_ENTRANTS} entrants.")
    if stage.format == Stage.Format.DOUBLE_ELIMINATION:
        return generate_double_elimination(
            count, grand_final_policy=stage.grand_final_policy
        )
    return generate_single_elimination(count)


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


def _validate_saved_draw(draw: StageDraw) -> None:
    if draw.stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
        from .swiss_commands import validate_swiss_draw

        validate_swiss_draw(draw)
        return
    if draw.stage.format == Stage.Format.ROUND_ROBIN:
        seeds = list(draw.entries.order_by("seed").values_list("seed", flat=True))
        if seeds != list(range(1, len(seeds) + 1)):
            raise ValidationError("The saved draw has invalid seeds.")
        from .round_robin_commands import validate_round_robin_draw
        from .stage_commands import resolve_group_sizes

        plans = list(draw.stage.group_plans.all())
        sizes = resolve_group_sizes(
            [(p.name, p.size, p.qualifying_places) for p in plans], len(seeds)
        )
        if [
            (g.name, g.entries.count(), g.qualifying_places) for g in draw.groups.all()
        ] != [
            (p.name, size, p.qualifying_places)
            for p, size in zip(plans, sizes, strict=True)
        ]:
            raise ValidationError(
                "The saved groups do not match the locked stage plan."
            )
        validate_round_robin_draw(draw)
        return
    entries = list(draw.entries.order_by("seed"))
    if [entry.seed for entry in entries] != list(range(1, len(entries) + 1)):
        raise ValidationError("The saved draw has invalid seeds.")
    expected = _generate_elimination(draw.stage, len(entries))
    matches = _ordered_matches(draw, include_drafts=True)
    by_key = {(m.round.section, m.round.number, m.number): m for m in matches}
    expected_keys = {
        (r.section, r.number, m.number) for r in expected for m in r.matches
    }
    if set(by_key) != expected_keys or set(
        draw.rounds.values_list("section", "number")
    ) != {(r.section, r.number) for r in expected}:
        raise ValidationError(
            "The saved draw does not match the stage format and policy."
        )
    entries_by_seed = {entry.seed: entry.pk for entry in entries}
    for round_ in expected:
        for generated in round_.matches:
            match = by_key[(round_.section, round_.number, generated.number)]
            slots = list(match.slots.order_by("position"))
            if [slot.position for slot in slots] != [1, 2]:
                raise ValidationError("The saved draw is incomplete.")
            for slot, source in zip(slots, generated.slots):
                if isinstance(source, SeedSlot):
                    entry_id = entries_by_seed.get(source.seed)
                    valid = (
                        slot.entry_id == entry_id
                        and slot.source_match_id is None
                        and slot.is_empty == (entry_id is None)
                        and slot.source_outcome == ""
                    )
                else:
                    source_match = by_key[
                        (source.section, source.round_number, source.match_number)
                    ]
                    outcome = (
                        MatchSlot.SourceOutcome.LOSER
                        if isinstance(source, LoserSlot)
                        else MatchSlot.SourceOutcome.WINNER
                    )
                    valid = (
                        slot.source_match_id == source_match.pk
                        and slot.source_outcome == outcome
                        and slot.entry_id is None
                        and not slot.is_empty
                    )
                if not valid:
                    raise ValidationError(
                        "The saved draw routing does not match the stage format and policy."
                    )


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


def _reconcile_reset_final(match: Match) -> None:
    if match.round.section != Round.Section.FINALS or match.round.number != 2:
        return
    first = Match.objects.get(
        round__draw=match.round.draw,
        round__section=Round.Section.FINALS,
        round__number=1,
        number=1,
    )
    status = _reset_final_status(
        first_status=first.status,
        first_outcome=first.outcome,
        winner_id=first.winner_id,
        lower_entry_id=first.slots.get(position=2).resolved_entry_id,
        status=match.status,
    )
    if match.status != status:
        match.status = status
        match.save(update_fields=("status",))


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


def _resolve_automatic_matches(draw: StageDraw) -> None:
    if draw.stage.format == Stage.Format.ROUND_ROBIN:
        return
    now = timezone.now()
    is_swiss = draw.stage.format in (
        Stage.Format.SWISS_FIXED,
        Stage.Format.SWISS_THRESHOLD,
    )
    for match in _ordered_matches(draw, include_drafts=not is_swiss):
        _reconcile_reset_final(match)
        result = _automatic_result(
            match.status,
            list(
                match.slots.order_by("position").values_list(
                    "is_resolved", "resolved_entry_id"
                )
            ),
        )
        if result is None:
            continue
        match.status = Match.Status.FINAL
        match.outcome, match.winner_id = result
        match.completed_at = now
        match.side_one_score = match.side_two_score = None
        match.save(
            update_fields=(
                "status",
                "outcome",
                "winner",
                "completed_at",
                "side_one_score",
                "side_two_score",
            )
        )
        _propagate_completed_match(match)


def _routed_entry_id(outcome, winner_id, entries, source_outcome):
    if source_outcome == MatchSlot.SourceOutcome.WINNER:
        return winner_id
    if outcome not in (Match.Outcome.PLAYED, Match.Outcome.FORFEIT) or not winner_id:
        return None
    return next((entry_id for entry_id in entries if entry_id != winner_id), None)


def _losing_entry_id(match: Match) -> int | None:
    return _routed_entry_id(
        match.outcome,
        match.winner_id,
        match.slots.order_by("position").values_list("resolved_entry_id", flat=True),
        MatchSlot.SourceOutcome.LOSER,
    )


def _propagate_completed_match(match: Match) -> None:
    MatchSlot.objects.filter(
        source_match=match, source_outcome=MatchSlot.SourceOutcome.WINNER
    ).update(is_resolved=True, resolved_entry=match.winner)
    MatchSlot.objects.filter(
        source_match=match, source_outcome=MatchSlot.SourceOutcome.LOSER
    ).update(is_resolved=True, resolved_entry_id=_losing_entry_id(match))


def _match_competition_id(match_id: int) -> int:
    return Match.objects.values_list(
        "round__draw__stage__competition_id", flat=True
    ).get(pk=match_id)


def _lock_match(match_id: int) -> tuple[Competition, Match]:
    competition = _lock_competition(_match_competition_id(match_id))
    match = (
        Match.objects.select_for_update()
        .select_related("round__draw__stage")
        .get(pk=match_id)
    )
    list(MatchSlot.objects.select_for_update().filter(match=match).order_by("position"))
    if match.round.draw.state != StageDraw.State.PUBLISHED:
        raise ValidationError("Only published matches can be operated.")
    _check_current_tie_match(match)
    _validate_threshold_match(match)
    return competition, match


def _validate_threshold_match(match):
    if match.round.draw.stage.format == Stage.Format.SWISS_THRESHOLD:
        if match.effective_series_mode != Stage.SeriesMode.BEST_OF:
            raise ValidationError("Threshold Swiss requires decisive best-of matches.")
        _validate_series_length(
            match.effective_series_mode, match.effective_series_length
        )


def _check_current_tie_match(match):
    if match.round.state != Round.State.PUBLISHED:
        raise ValidationError("Only current published rounds can be operated.")
    if (
        match.round.tie_resolution_id
        and match.round.tie_resolution.state == TieResolution.State.SUPERSEDED
    ):
        raise ValidationError(
            "Superseded tie contests are historical and cannot be operated."
        )


def schedule_match(
    *, actor, match_id: int, expected_revision: int, scheduled_at
) -> Match:
    require_organizer(actor, "competitions.change_match")
    with transaction.atomic():
        competition, match = _lock_match(match_id)
        _check_revision(competition, expected_revision)
        if match.status not in (
            Match.Status.PENDING,
            Match.Status.CONDITIONAL,
            Match.Status.NOT_REQUIRED,
        ):
            raise ValidationError("Only an unstarted match can be rescheduled.")
        match.scheduled_at = scheduled_at
        match.save(update_fields=("scheduled_at",))
        _record_change(
            competition,
            actor=actor,
            kind="match_scheduled",
            private_data={"match_id": match.pk},
            public_data={
                "kind": "match_scheduled",
                "match_id": match.pk,
                "match_code": match.code,
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            },
        )
        return match


def set_round_series_length(
    *, actor, round_id: int, expected_revision: int, series_length: int | None
) -> Round:
    require_organizer(actor, "competitions.change_match")
    competition_id = Round.objects.values_list(
        "draw__stage__competition_id", flat=True
    ).get(pk=round_id)
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        round_ = (
            Round.objects.select_for_update()
            .select_related("draw__stage")
            .get(pk=round_id)
        )
        if (
            round_.draw.state != StageDraw.State.PUBLISHED
            or round_.state != Round.State.PUBLISHED
        ):
            raise ValidationError("Only a published round can be changed.")
        if (
            round_.tie_resolution_id
            and round_.tie_resolution.state == TieResolution.State.SUPERSEDED
        ):
            raise ValidationError("Superseded tie rounds are historical.")
        inherited_length = (
            series_length
            if series_length is not None
            else round_.draw.stage.default_series_length
        )
        if (
            round_.draw.stage.format == Stage.Format.SWISS_THRESHOLD
            and (round_.series_mode_override or round_.draw.stage.series_mode)
            != Stage.SeriesMode.BEST_OF
        ):
            raise ValidationError("Threshold Swiss requires decisive best-of matches.")
        _validate_series_length(
            round_.series_mode_override or round_.draw.stage.series_mode,
            inherited_length,
        )
        if (
            round_.matches.filter(
                started_at__isnull=False,
                series_length_override__isnull=True,
            )
            .exclude(applied_series_length=inherited_length)
            .exists()
        ):
            raise ValidationError("This change would reinterpret a started match.")
        round_.series_length_override = series_length
        round_.save(update_fields=("series_length_override",))
        _record_change(
            competition,
            actor=actor,
            kind="round_series_length_changed",
            private_data={"round_id": round_.pk, "series_length": series_length},
            public_data={
                "kind": "round_series_length_changed",
                "round_id": round_.pk,
                "series_length": series_length,
            },
        )
        return round_


def set_match_series_length(
    *, actor, match_id: int, expected_revision: int, series_length: int | None
) -> Match:
    require_organizer(actor, "competitions.change_match")
    with transaction.atomic():
        competition, match = _lock_match(match_id)
        _check_revision(competition, expected_revision)
        if match.started_at is not None:
            raise ValidationError("A started match keeps its applied series length.")
        _validate_series_length(
            match.effective_series_mode,
            series_length
            if series_length is not None
            else match.round.series_length_override
            or match.round.draw.stage.default_series_length,
        )
        match.series_length_override = series_length
        match.save(update_fields=("series_length_override",))
        _record_change(
            competition,
            actor=actor,
            kind="match_series_length_changed",
            private_data={"match_id": match.pk, "series_length": series_length},
            public_data={
                "kind": "match_series_length_changed",
                "match_id": match.pk,
                "match_code": match.code,
                "series_length": series_length,
            },
        )
        return match


def _playable_slots(match: Match) -> list[MatchSlot]:
    if match.status in (Match.Status.CONDITIONAL, Match.Status.NOT_REQUIRED):
        raise ValidationError("An inactive reset final cannot be played.")
    slots = list(
        match.slots.select_related("resolved_entry__entrant").order_by("position")
    )
    if len(slots) != 2 or not all(
        slot.is_resolved and slot.resolved_entry_id for slot in slots
    ):
        raise ValidationError("Both match entrants must be resolved before play.")
    return slots


def start_match(*, actor, match_id: int, expected_revision: int) -> Match:
    require_organizer(actor, "competitions.change_match")
    with transaction.atomic():
        competition, match = _lock_match(match_id)
        _check_revision(competition, expected_revision)
        if match.status != Match.Status.PENDING:
            raise ValidationError("Only a pending match can start.")
        _playable_slots(match)
        now = timezone.now()
        match.status = Match.Status.LIVE
        match.started_at = now
        match.applied_series_mode = match.effective_series_mode
        match.applied_series_length = match.effective_series_length
        match.save(
            update_fields=(
                "status",
                "started_at",
                "applied_series_mode",
                "applied_series_length",
            )
        )
        stage = match.round.draw.stage
        stage.status = Stage.Status.IN_PROGRESS
        stage.save(update_fields=("status",))
        _record_change(
            competition,
            actor=actor,
            kind="match_started",
            private_data={"match_id": match.pk},
            public_data={
                "kind": "match_started",
                "match_id": match.pk,
                "match_code": match.code,
            },
        )
        return match


def save_match_progress(
    *,
    actor,
    match_id: int,
    expected_revision: int,
    side_one_score: int,
    side_two_score: int,
) -> Match:
    require_organizer(actor, "competitions.change_match")
    with transaction.atomic():
        competition, match = _lock_match(match_id)
        _check_revision(competition, expected_revision)
        if match.status == Match.Status.FINAL:
            raise ValidationError("A final match must be corrected instead.")
        _playable_slots(match)
        length = match.applied_series_length or match.effective_series_length
        target = length // 2 + 1
        _validate_scores(side_one_score, side_two_score)
        terminal = (
            side_one_score + side_two_score >= length
            if match.effective_series_mode == Stage.SeriesMode.FIXED_GAMES
            else max(side_one_score, side_two_score) >= target
        )
        if terminal:
            raise ValidationError("A terminal score must be finalized.")
        now = timezone.now()
        match.status = Match.Status.LIVE
        match.started_at = match.started_at or now
        match.applied_series_mode = match.effective_series_mode
        match.applied_series_length = length
        match.side_one_score = side_one_score
        match.side_two_score = side_two_score
        match.save(
            update_fields=(
                "status",
                "started_at",
                "applied_series_length",
                "applied_series_mode",
                "side_one_score",
                "side_two_score",
            )
        )
        stage = match.round.draw.stage
        stage.status = Stage.Status.IN_PROGRESS
        stage.save(update_fields=("status",))
        _record_change(
            competition,
            actor=actor,
            kind="match_progress_saved",
            private_data={"match_id": match.pk},
            public_data={
                "kind": "match_progress_saved",
                "match_id": match.pk,
                "match_code": match.code,
                "side_one_score": side_one_score,
                "side_two_score": side_two_score,
            },
        )
        return match


def _validate_scores(one, two, *, allow_empty=False):
    for score in (one, two):
        if score is None and allow_empty:
            continue
        if type(score) is not int or not 0 <= score <= 32767:
            raise ValidationError(
                "Scores must be nonnegative integers within the supported range."
            )


def _validate_result(
    match: Match,
    *,
    outcome: str,
    side_one_score: int | None,
    side_two_score: int | None,
    winner_position: int | None,
) -> tuple[StageEntry | None, int | None, int | None]:
    _validate_threshold_match(match)
    slots = _playable_slots(match)
    if outcome == Match.Outcome.PLAYED:
        _validate_scores(side_one_score, side_two_score)
        length = match.effective_series_length
        if match.effective_series_mode == Stage.SeriesMode.FIXED_GAMES:
            if side_one_score + side_two_score != length:
                raise ValidationError(
                    "A fixed-game final must contain exactly the configured games."
                )
            winner_position = (
                None
                if side_one_score == side_two_score
                else 1
                if side_one_score > side_two_score
                else 2
            )
        else:
            target = length // 2 + 1
            if (
                max(side_one_score, side_two_score) != target
                or min(side_one_score, side_two_score) >= target
            ):
                raise ValidationError(
                    "A final best-of score must have one winner at the win target."
                )
            winner_position = 1 if side_one_score > side_two_score else 2
    elif outcome == Match.Outcome.FORFEIT:
        if winner_position not in (1, 2):
            raise ValidationError("Choose the forfeit winner.")
        _validate_scores(side_one_score, side_two_score, allow_empty=True)
    elif outcome == Match.Outcome.DOUBLE_FORFEIT:
        winner_position = None
        _validate_scores(side_one_score, side_two_score, allow_empty=True)
    else:
        raise ValidationError("Choose a supported final outcome.")
    winner = slots[winner_position - 1].resolved_entry if winner_position else None
    return winner, side_one_score, side_two_score


def _update_stage_completion(draw: StageDraw) -> None:
    if draw.stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
        from .swiss_commands import update_swiss_completion

        update_swiss_completion(draw.stage, draw)
        return
    if draw.stage.format == Stage.Format.ROUND_ROBIN:
        from .round_robin_commands import update_round_robin_completion

        update_round_robin_completion(draw)
        return
    stage = draw.stage
    finals = Match.objects.filter(round__draw=draw)
    if stage.format == Stage.Format.DOUBLE_ELIMINATION:
        finals = finals.filter(round__section=Round.Section.FINALS)
        reset = finals.filter(round__number=2).first()
        final = (
            reset
            if stage.grand_final_policy == Stage.GrandFinalPolicy.RESET
            and reset
            and reset.status
            in (Match.Status.PENDING, Match.Status.LIVE, Match.Status.FINAL)
            else finals.get(round__number=1)
        )
    else:
        final = (
            finals.filter(round__section=Round.Section.NORMAL)
            .order_by("-round__number", "number")
            .first()
        )
    if final and final.status == Match.Status.FINAL:
        stage.status = Stage.Status.COMPLETE
        stage.champion = final.winner.entrant if final.winner_id else None
        stage.completed_without_champion = final.winner_id is None
        stage.completed_at = final.completed_at or timezone.now()
    else:
        stage.status = (
            Stage.Status.IN_PROGRESS
            if Match.objects.filter(round__draw=draw, started_at__isnull=False).exists()
            else Stage.Status.READY
        )
        stage.champion = None
        stage.completed_without_champion = False
        stage.completed_at = None
    if stage.advancement_count is not None:
        from .qualification import stage_qualification

        qualification = stage_qualification(draw)
        for resolution_id, status in qualification["resolution_states"].items():
            TieResolution.objects.filter(pk=resolution_id).update(
                state=status,
                confirmed_at=timezone.now() if status == "CONFIRMED" else None,
            )
        if qualification["qualification_state"] != "RESOLVED":
            stage.status = (
                Stage.Status.AWAITING
                if qualification["qualification_state"]
                in ("AWAITING_RESOLUTION", "BLOCKED")
                else Stage.Status.IN_PROGRESS
            )
            stage.completed_at = None
    stage.save(
        update_fields=(
            "status",
            "champion",
            "completed_without_champion",
            "completed_at",
        )
    )


def finalize_match(
    *,
    actor,
    match_id: int,
    expected_revision: int,
    outcome: str,
    side_one_score: int | None = None,
    side_two_score: int | None = None,
    winner_position: int | None = None,
) -> Match:
    require_organizer(actor, "competitions.change_match")
    with transaction.atomic():
        competition, match = _lock_match(match_id)
        _check_revision(competition, expected_revision)
        if match.status == Match.Status.FINAL:
            raise ValidationError("This match is already final.")
        winner, side_one_score, side_two_score = _validate_result(
            match,
            outcome=outcome,
            side_one_score=side_one_score,
            side_two_score=side_two_score,
            winner_position=winner_position,
        )
        now = timezone.now()
        match.status = Match.Status.FINAL
        match.started_at = match.started_at or now
        match.completed_at = now
        match.applied_series_mode = match.effective_series_mode
        match.applied_series_length = (
            match.applied_series_length or match.effective_series_length
        )
        match.side_one_score = side_one_score
        match.side_two_score = side_two_score
        match.outcome = outcome
        match.winner = winner
        match.save(
            update_fields=(
                "status",
                "started_at",
                "completed_at",
                "applied_series_length",
                "applied_series_mode",
                "side_one_score",
                "side_two_score",
                "outcome",
                "winner",
            )
        )
        _propagate_completed_match(match)
        _resolve_automatic_matches(match.round.draw)
        _update_stage_completion(match.round.draw)
        _record_change(
            competition,
            actor=actor,
            kind="match_finalized",
            private_data={"match_id": match.pk},
            public_data={
                "kind": "match_finalized",
                "match_id": match.pk,
                "match_code": match.code,
                "side_one_score": side_one_score,
                "side_two_score": side_two_score,
                "outcome": outcome,
                "winner": winner.entrant.display_name if winner else None,
            },
        )
        return match


def _project_correction(match: Match, *, outcome, winner_id):
    """Re-resolve competitive inputs; invalidate only contests whose inputs change."""
    ordered = _ordered_matches(match.round.draw)
    slots_by_match = {item.pk: [] for item in ordered}
    for slot in MatchSlot.objects.filter(match_id__in=slots_by_match).order_by(
        "position"
    ):
        slots_by_match[slot.match_id].append(slot)
    projected = {}
    affected, impacts, reset_changes = [], [], []
    first_final_id = next(
        (
            item.pk
            for item in ordered
            if item.round.section == Round.Section.FINALS and item.round.number == 1
        ),
        None,
    )
    for item in ordered:
        saved_slots = [
            [slot.is_resolved, slot.resolved_entry_id]
            for slot in slots_by_match[item.pk]
        ]
        slots = []
        for slot in slots_by_match[item.pk]:
            if slot.source_match_id:
                source = projected[slot.source_match_id]
                resolved = source["status"] == Match.Status.FINAL
                entry_id = (
                    _routed_entry_id(
                        source["outcome"],
                        source["winner_id"],
                        [entry for _, entry in source["slots"]],
                        slot.source_outcome,
                    )
                    if resolved
                    else None
                )
                slots.append([resolved, entry_id])
            else:
                slots.append([slot.is_resolved, slot.resolved_entry_id])
        state = {
            "status": item.status,
            "outcome": item.outcome,
            "winner_id": item.winner_id,
            "slots": slots,
        }
        if item.pk == match.pk:
            state.update(outcome=outcome, winner_id=winner_id)
        else:
            changed_inputs = slots != saved_slots
            status = Match.Status.PENDING if changed_inputs else item.status
            is_reset = (
                item.round.section == Round.Section.FINALS and item.round.number == 2
            )
            if is_reset:
                first = projected[first_final_id]
                status = _reset_final_status(
                    first_status=first["status"],
                    first_outcome=first["outcome"],
                    winner_id=first["winner_id"],
                    lower_entry_id=first["slots"][1][1],
                    status=status,
                )
                before, after = (
                    _reset_activation(item.status),
                    _reset_activation(status),
                )
                if before != after:
                    reset_changes.append(
                        {
                            "match_id": item.pk,
                            "match_code": item.code,
                            "before": before,
                            "after": after,
                        }
                    )
            if changed_inputs or status != item.status:
                state.update(status=status, outcome="", winner_id=None)
                result = _automatic_result(status, slots)
                if result is not None:
                    state.update(
                        status=Match.Status.FINAL,
                        outcome=result[0],
                        winner_id=result[1],
                    )
                affected.append(item)
                impacts.append(
                    {
                        "match_id": item.pk,
                        "before": _match_snapshot(item),
                        "before_slots": saved_slots,
                        "after_slots": slots,
                        "after_status": state["status"],
                    }
                )
        projected[item.pk] = state
    return affected, impacts, reset_changes, projected


def _correction_payload(
    match: Match,
    *,
    competition_revision: int,
    outcome: str,
    side_one_score: int | None,
    side_two_score: int | None,
    winner_position: int | None,
) -> tuple[dict, StageEntry | None, list[Match]]:
    if match.round.draw.state != StageDraw.State.PUBLISHED:
        raise ValidationError("Only current published matches can be corrected.")
    _check_current_tie_match(match)
    if match.status != Match.Status.FINAL or match.outcome in (
        Match.Outcome.BYE,
        Match.Outcome.EMPTY,
    ):
        raise ValidationError("Only an entered final result can be corrected.")
    winner, side_one_score, side_two_score = _validate_result(
        match,
        outcome=outcome,
        side_one_score=side_one_score,
        side_two_score=side_two_score,
        winner_position=winner_position,
    )
    group_impact = None
    if match.round.draw.stage.format == Stage.Format.ROUND_ROBIN:
        from .round_robin_commands import project_group_correction

        group_impact = project_group_correction(
            match,
            outcome=outcome,
            side_one_score=side_one_score,
            side_two_score=side_two_score,
            winner_entry_id=winner.pk if winner else None,
        )
        affected, impacts, reset_changes, projected = [], [], [], {}
    else:
        affected, impacts, reset_changes, projected = _project_correction(
            match,
            outcome=outcome,
            winner_id=winner.pk if winner else None,
        )
    from .qualification import stage_qualification
    from .handoff_commands import project_handoff_corrections

    projected.setdefault(match.pk, {}).update(
        status="FINAL",
        outcome=outcome,
        side_one_score=side_one_score,
        side_two_score=side_two_score,
        winner_id=winner.pk if winner else None,
    )
    qualification = stage_qualification(match.round.draw, projected_matches=projected)
    handoff_impact = project_handoff_corrections(
        match.round.draw,
        projected_qualification=qualification,
        source_needs_replay=qualification["qualification_state"] == "PROVISIONAL",
    )
    invalidated_ties = []
    if match.round.draw.stage.format != Stage.Format.ROUND_ROBIN:
        active = list(
            match.round.draw.tie_resolutions.exclude(state="SUPERSEDED").values_list(
                "pk", flat=True
            )
        )
        invalidated_ties = [
            pk for pk in active if pk not in qualification["resolution_states"]
        ]
    payload = {
        "competition_id": match.round.draw.stage.competition_id,
        "revision": competition_revision,
        "match_id": match.pk,
        "outcome": outcome,
        "side_one_score": side_one_score,
        "side_two_score": side_two_score,
        "winner_entry_id": winner.pk if winner else None,
        "affected_match_ids": [item.pk for item in affected],
        "before": _match_snapshot(match),
        "match_impacts": impacts,
        "reset_final_changes": reset_changes,
        "group_impact": group_impact,
        "handoff_impact": handoff_impact,
        "invalidated_tie_ids": invalidated_ties,
    }
    return payload, winner, affected


def preview_correction(
    *,
    actor,
    match_id: int,
    expected_revision: int,
    outcome: str,
    side_one_score: int | None = None,
    side_two_score: int | None = None,
    winner_position: int | None = None,
) -> dict:
    require_organizer(actor, "competitions.change_match")
    require_organizer(actor, "competitions.change_competition")
    match = Match.objects.select_related(
        "round__draw__stage__competition", "winner__entrant"
    ).get(pk=match_id)
    competition = match.round.draw.stage.competition
    _check_revision(competition, expected_revision)
    payload, winner, affected = _correction_payload(
        match,
        competition_revision=competition.revision,
        outcome=outcome,
        side_one_score=side_one_score,
        side_two_score=side_two_score,
        winner_position=winner_position,
    )
    return _correction_preview_response(match, payload, winner, affected)


def _correction_preview_response(
    match: Match,
    payload: dict,
    winner: StageEntry | None,
    affected: list[Match],
    *,
    token: str | None = None,
) -> dict:
    return {
        "token": token or signing.dumps(payload, salt=CORRECTION_SALT, compress=True),
        "before": _match_snapshot(match),
        "after": {
            **_match_snapshot(match),
            "outcome": payload["outcome"],
            "side_one_score": payload["side_one_score"],
            "side_two_score": payload["side_two_score"],
            "winner": winner.entrant.display_name if winner else None,
        },
        "affected_matches": [_match_snapshot(item) for item in affected],
        "match_impacts": payload["match_impacts"],
        "reset_final_changes": payload["reset_final_changes"],
        "group_impact": payload["group_impact"],
        "handoff_impact": payload["handoff_impact"],
    }


def _load_correction_token(token: str) -> dict:
    try:
        return signing.loads(token, salt=CORRECTION_SALT, max_age=3600)
    except signing.BadSignature as error:
        raise ValidationError(
            "The correction preview is invalid or expired."
        ) from error


def _submitted_winner_position(match: Match, submitted: dict) -> int | None:
    if not submitted["winner_entry_id"]:
        return None
    return next(
        (
            slot.position
            for slot in match.slots.all()
            if slot.resolved_entry_id == submitted["winner_entry_id"]
        ),
        None,
    )


def review_correction_preview(*, actor, token: str) -> dict:
    require_organizer(actor, "competitions.change_match")
    require_organizer(actor, "competitions.change_competition")
    submitted = _load_correction_token(token)
    match = Match.objects.select_related(
        "round__draw__stage__competition", "winner__entrant"
    ).get(pk=submitted["match_id"])
    competition = match.round.draw.stage.competition
    _check_revision(competition, submitted["revision"])
    current, winner, affected = _correction_payload(
        match,
        competition_revision=competition.revision,
        outcome=submitted["outcome"],
        side_one_score=submitted["side_one_score"],
        side_two_score=submitted["side_two_score"],
        winner_position=_submitted_winner_position(match, submitted),
    )
    if current != submitted:
        raise ValidationError("The correction impact changed. Preview it again.")
    return _correction_preview_response(match, current, winner, affected, token=token)


def apply_correction(*, actor, token: str, internal_reason: str) -> Match:
    require_organizer(actor, "competitions.change_match")
    require_organizer(actor, "competitions.change_competition")
    if not internal_reason.strip():
        raise ValidationError("An internal correction reason is required.")
    submitted = _load_correction_token(token)
    with transaction.atomic():
        competition, match = _lock_match(submitted["match_id"])
        _check_revision(competition, submitted["revision"])
        list(
            Match.objects.select_for_update()
            .filter(round__draw=match.round.draw)
            .order_by("pk")
        )
        list(
            MatchSlot.objects.select_for_update()
            .filter(match__round__draw=match.round.draw)
            .order_by("pk")
        )
        current, winner, affected = _correction_payload(
            match,
            competition_revision=competition.revision,
            outcome=submitted["outcome"],
            side_one_score=submitted["side_one_score"],
            side_two_score=submitted["side_two_score"],
            winner_position=_submitted_winner_position(match, submitted),
        )
        if current != submitted:
            raise ValidationError("The correction impact changed. Preview it again.")
        before = _match_snapshot(match)
        reset_snapshots = [
            _match_snapshot(item)
            for item in affected
            if item.status in (Match.Status.LIVE, Match.Status.FINAL)
        ]
        affected_ids = [item.pk for item in affected]
        if affected_ids:
            Match.objects.filter(pk__in=affected_ids).update(
                status=Match.Status.PENDING,
                applied_series_length=None,
                side_one_score=None,
                side_two_score=None,
                outcome="",
                winner=None,
                started_at=None,
                completed_at=None,
            )
            for impact in current["match_impacts"]:
                for position, (resolved, entry_id) in enumerate(
                    impact["after_slots"], start=1
                ):
                    MatchSlot.objects.filter(
                        match_id=impact["match_id"], position=position
                    ).update(
                        is_resolved=resolved,
                        resolved_entry_id=entry_id,
                    )
        match.outcome = submitted["outcome"]
        match.side_one_score = submitted["side_one_score"]
        match.side_two_score = submitted["side_two_score"]
        match.winner = winner
        match.completed_at = timezone.now()
        match.save(
            update_fields=(
                "outcome",
                "side_one_score",
                "side_two_score",
                "winner",
                "completed_at",
            )
        )
        if current["group_impact"]:
            from .round_robin_commands import apply_group_correction_impact

            apply_group_correction_impact(match, current["group_impact"])
        _supersede_ties(
            TieResolution.objects.filter(pk__in=current["invalidated_tie_ids"])
        )
        from .handoff_commands import apply_handoff_impact, public_handoff_impact

        apply_handoff_impact(current["handoff_impact"])
        _propagate_completed_match(match)
        _resolve_automatic_matches(match.round.draw)
        _update_stage_completion(match.round.draw)
        _record_change(
            competition,
            actor=actor,
            kind="result_corrected",
            internal_reason=internal_reason,
            private_data={
                "match_id": match.pk,
                "before": before,
                "after": _match_snapshot(match),
                "reset_matches": reset_snapshots,
                "reset_final_changes": current["reset_final_changes"],
                "group_impact": current["group_impact"],
                "handoff_impact": current["handoff_impact"],
            },
            public_data={
                "kind": "result_corrected",
                "match_id": match.pk,
                "match_code": match.code,
                "before": before,
                "after": _match_snapshot(match),
                "reset_matches": reset_snapshots,
                "reset_final_changes": current["reset_final_changes"],
                "group_impact": current["group_impact"],
                "handoff_impact": public_handoff_impact(current["handoff_impact"]),
            },
        )
        return match
