from __future__ import annotations

import secrets
from collections import deque
from collections.abc import Sequence

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from config.organizers import require_organizer
from registrations.models import Registration
from tournaments.models import TournamentGame

from .elimination import SeedSlot, WinnerSlot, generate_single_elimination
from .models import (
    ChangeSet,
    Competition,
    CompetitionEntrant,
    Match,
    MatchSlot,
    Round,
    Stage,
    StageDraw,
    StageEntry,
)

CORRECTION_SALT = "competitions.correction"
MAX_ENTRANTS = 256
MAX_MATCHES = 16_384


def _lock_competition(competition_id: int) -> Competition:
    division_id = Competition.objects.values_list(
        "tournament_game_id", flat=True
    ).get(pk=competition_id)
    # ponytail: one division lock serializes competition and registration writes;
    # use finer locks only if measured event throughput requires them.
    TournamentGame.objects.select_for_update().get(pk=division_id)
    return Competition.objects.select_for_update().select_related(
        "tournament_game", "tournament_game__tournament", "tournament_game__game"
    ).get(pk=competition_id)


def _check_revision(competition: Competition, expected_revision: int) -> None:
    if competition.revision != expected_revision:
        raise ValidationError(
            f"Competition changed from revision {expected_revision} "
            f"to {competition.revision}. Reload and try again."
        )


def _record_change(
    competition: Competition,
    *,
    actor,
    kind: str,
    private_data: dict | None = None,
    public_data: dict | None = None,
    internal_reason: str = "",
) -> ChangeSet:
    competition.revision += 1
    competition.save(update_fields=("revision", "updated_at"))
    return ChangeSet.objects.create(
        competition=competition,
        revision=competition.revision,
        kind=kind,
        actor=actor,
        internal_reason=internal_reason.strip(),
        private_data=private_data or {},
        public_data=public_data or {},
    )


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


def configure_single_elimination(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    name: str,
    default_series_length: int,
) -> Stage:
    require_organizer(actor, "competitions.change_competition")
    name = name.strip()
    if not name:
        raise ValidationError({"name": "Enter a stage name."})
    _validate_best_of(default_series_length)
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = Stage.objects.select_for_update().filter(
            competition=competition, sequence=1
        ).first()
        if stage and stage.published_at:
            raise ValidationError("Published stage setup is locked.")
        if stage is None:
            stage = Stage.objects.create(
                competition=competition,
                sequence=1,
                name=name,
                format=Stage.Format.SINGLE_ELIMINATION,
                series_mode=Stage.SeriesMode.BEST_OF,
                default_series_length=default_series_length,
            )
        else:
            stage.name = name
            stage.default_series_length = default_series_length
            stage.save(update_fields=("name", "default_series_length"))
        _record_change(
            competition,
            actor=actor,
            kind="stage_configured",
            private_data={
                "stage_id": stage.pk,
                "name": stage.name,
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
        if StageDraw.objects.filter(stage__competition=competition).exists():
            raise ValidationError("Entrants cannot change after a draw is saved.")
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
        competition.entrants.all().delete()
        entrants = []
        for registration_id in unique_ids:
            registration = by_id[registration_id]
            display_name, display_tag = _entrant_label(registration)
            entrants.append(
                CompetitionEntrant.objects.create(
                    competition=competition,
                    registration=registration,
                    display_name=display_name,
                    display_tag=display_tag,
                )
            )
        _record_change(
            competition,
            actor=actor,
            kind="entrants_selected",
            private_data={"registration_ids": unique_ids},
        )
        return entrants


def save_single_elimination_draw(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    entrant_order: Sequence[int] | None = None,
    randomize: bool = False,
) -> StageDraw:
    require_organizer(actor, "competitions.change_competition")
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = Stage.objects.select_for_update().filter(
            competition=competition, sequence=1
        ).first()
        if stage is None:
            raise ValidationError("Configure the stage before saving a draw.")
        if stage.published_at:
            raise ValidationError("The published draw cannot be replaced directly.")
        entrants = list(
            CompetitionEntrant.objects.select_for_update()
            .filter(competition=competition, status=CompetitionEntrant.Status.ACTIVE)
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
        generated = generate_single_elimination(len(entrants))
        if sum(len(round_.matches) for round_ in generated) > MAX_MATCHES:
            raise ValidationError("The generated draw exceeds the match limit.")
        current = StageDraw.objects.select_for_update().filter(
            stage=stage, state=StageDraw.State.DRAFT
        ).first()
        next_version = (
            StageDraw.objects.filter(stage=stage).order_by("-version").values_list(
                "version", flat=True
            ).first()
            or 0
        ) + 1
        if current:
            current.state = StageDraw.State.SUPERSEDED
            current.save(update_fields=("state",))
        draw = StageDraw.objects.create(
            stage=stage, version=next_version, randomized=randomize
        )
        entrants_by_id = {entrant.pk: entrant for entrant in entrants}
        entries_by_seed = {
            seed: StageEntry.objects.create(
                draw=draw, entrant=entrants_by_id[entrant_id], seed=seed
            )
            for seed, entrant_id in enumerate(ordered_ids, start=1)
        }
        matches: dict[tuple[int, int], Match] = {}
        for generated_round in generated:
            round_ = Round.objects.create(draw=draw, number=generated_round.number)
            for generated_match in generated_round.matches:
                match = Match.objects.create(
                    round=round_,
                    number=generated_match.number,
                    code=(
                        f"C{competition.pk}-D{draw.version}-"
                        f"R{round_.number}-M{generated_match.number}"
                    ),
                )
                matches[(round_.number, match.number)] = match
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
                    elif isinstance(slot, WinnerSlot):
                        MatchSlot.objects.create(
                            match=match,
                            position=position,
                            source_match=matches[
                                (slot.round_number, slot.match_number)
                            ],
                            source_outcome=MatchSlot.SourceOutcome.WINNER,
                        )
        _resolve_automatic_matches(draw)
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


def publish_draw(
    *, actor, competition_id: int, expected_revision: int
) -> StageDraw:
    require_organizer(actor, "competitions.change_competition")
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = Stage.objects.select_for_update().get(
            competition=competition, sequence=1
        )
        if stage.published_at:
            raise ValidationError("This stage is already published.")
        draw = StageDraw.objects.select_for_update().get(
            stage=stage, state=StageDraw.State.DRAFT
        )
        registration_ids = list(
            competition.entrants.order_by("registration_id").values_list(
                "registration_id", flat=True
            )
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
            raise ValidationError("Every entrant must still be approved for this division.")
        if draw.entries.count() != len(registration_ids):
            raise ValidationError("The draw does not contain every selected entrant.")
        match_count = Match.objects.filter(round__draw=draw).count()
        slot_count = MatchSlot.objects.filter(match__round__draw=draw).count()
        if match_count == 0 or slot_count != match_count * 2:
            raise ValidationError("The saved draw is incomplete.")
        now = timezone.now()
        draw.state = StageDraw.State.PUBLISHED
        draw.published_at = now
        draw.save(update_fields=("state", "published_at"))
        stage.status = Stage.Status.READY
        stage.published_at = now
        stage.save(update_fields=("status", "published_at"))
        _record_change(
            competition,
            actor=actor,
            kind="draw_published",
            private_data={"draw_id": draw.pk},
            public_data={
                "kind": "draw_published",
                "stage_id": stage.pk,
                "draw_id": draw.pk,
            },
        )
        return draw


def _validate_best_of(length: int) -> None:
    if length < 1 or length % 2 == 0:
        raise ValidationError("Best-of length must be a positive odd number.")


def _resolve_automatic_matches(draw: StageDraw) -> None:
    now = timezone.now()
    for match in Match.objects.filter(round__draw=draw).order_by(
        "round__number", "number"
    ):
        if match.status == Match.Status.FINAL:
            continue
        slots = list(match.slots.order_by("position"))
        if len(slots) != 2 or not all(slot.is_resolved for slot in slots):
            continue
        entries = [slot.resolved_entry for slot in slots if slot.resolved_entry_id]
        if len(entries) == 2:
            continue
        match.status = Match.Status.FINAL
        match.outcome = Match.Outcome.BYE if entries else Match.Outcome.EMPTY
        match.winner = entries[0] if entries else None
        match.completed_at = now
        match.save(
            update_fields=("status", "outcome", "winner", "completed_at")
        )
        _propagate_completed_match(match)


def _propagate_completed_match(match: Match) -> None:
    MatchSlot.objects.filter(source_match=match).update(
        is_resolved=True, resolved_entry=match.winner
    )


def _match_competition_id(match_id: int) -> int:
    return Match.objects.values_list(
        "round__draw__stage__competition_id", flat=True
    ).get(pk=match_id)


def _lock_match(match_id: int) -> tuple[Competition, Match]:
    competition = _lock_competition(_match_competition_id(match_id))
    match = Match.objects.select_for_update().select_related(
        "round__draw__stage"
    ).get(pk=match_id)
    list(MatchSlot.objects.select_for_update().filter(match=match).order_by("position"))
    if match.round.draw.state != StageDraw.State.PUBLISHED:
        raise ValidationError("Only published matches can be operated.")
    return competition, match


def schedule_match(
    *, actor, match_id: int, expected_revision: int, scheduled_at
) -> Match:
    require_organizer(actor, "competitions.change_match")
    with transaction.atomic():
        competition, match = _lock_match(match_id)
        _check_revision(competition, expected_revision)
        if match.status != Match.Status.PENDING:
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
    if series_length is not None:
        _validate_best_of(series_length)
    competition_id = Round.objects.values_list(
        "draw__stage__competition_id", flat=True
    ).get(pk=round_id)
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        round_ = Round.objects.select_for_update().select_related("draw__stage").get(
            pk=round_id
        )
        if round_.draw.state != StageDraw.State.PUBLISHED:
            raise ValidationError("Only a published round can be changed.")
        inherited_length = series_length or round_.draw.stage.default_series_length
        if round_.matches.filter(
            started_at__isnull=False,
            series_length_override__isnull=True,
        ).exclude(applied_series_length=inherited_length).exists():
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
    if series_length is not None:
        _validate_best_of(series_length)
    with transaction.atomic():
        competition, match = _lock_match(match_id)
        _check_revision(competition, expected_revision)
        if match.started_at is not None:
            raise ValidationError("A started match keeps its applied series length.")
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
        match.applied_series_length = match.effective_series_length
        match.save(
            update_fields=("status", "started_at", "applied_series_length")
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
        if min(side_one_score, side_two_score) < 0:
            raise ValidationError("Scores cannot be negative.")
        if max(side_one_score, side_two_score) >= target:
            raise ValidationError("A terminal score must be finalized.")
        now = timezone.now()
        match.status = Match.Status.LIVE
        match.started_at = match.started_at or now
        match.applied_series_length = length
        match.side_one_score = side_one_score
        match.side_two_score = side_two_score
        match.save(
            update_fields=(
                "status",
                "started_at",
                "applied_series_length",
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


def _validate_result(
    match: Match,
    *,
    outcome: str,
    side_one_score: int | None,
    side_two_score: int | None,
    winner_position: int | None,
) -> tuple[StageEntry | None, int | None, int | None]:
    slots = _playable_slots(match)
    if outcome == Match.Outcome.PLAYED:
        if side_one_score is None or side_two_score is None:
            raise ValidationError("Played results require both scores.")
        if min(side_one_score, side_two_score) < 0:
            raise ValidationError("Scores cannot be negative.")
        length = match.applied_series_length or match.effective_series_length
        target = length // 2 + 1
        if sorted((side_one_score, side_two_score), reverse=True)[0] != target:
            raise ValidationError("A final best-of score must reach the win target.")
        if side_one_score == side_two_score or min(side_one_score, side_two_score) >= target:
            raise ValidationError("A final best-of score must have one winner.")
        winner_position = 1 if side_one_score > side_two_score else 2
    elif outcome == Match.Outcome.FORFEIT:
        if winner_position not in (1, 2):
            raise ValidationError("Choose the forfeit winner.")
        for score in (side_one_score, side_two_score):
            if score is not None and score < 0:
                raise ValidationError("Scores cannot be negative.")
    elif outcome == Match.Outcome.DOUBLE_FORFEIT:
        winner_position = None
        for score in (side_one_score, side_two_score):
            if score is not None and score < 0:
                raise ValidationError("Scores cannot be negative.")
    else:
        raise ValidationError("Choose a supported final outcome.")
    winner = slots[winner_position - 1].resolved_entry if winner_position else None
    return winner, side_one_score, side_two_score


def _update_stage_completion(draw: StageDraw) -> None:
    stage = draw.stage
    final = Match.objects.filter(round__draw=draw).order_by(
        "-round__number", "number"
    ).first()
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


def _match_snapshot(match: Match) -> dict:
    slots = list(
        match.slots.select_related("resolved_entry__entrant").order_by("position")
    )
    return {
        "match_id": match.pk,
        "match_code": match.code,
        "status": match.status,
        "outcome": match.outcome,
        "side_one": (
            slots[0].resolved_entry.entrant.display_name
            if len(slots) > 0 and slots[0].resolved_entry_id
            else None
        ),
        "side_two": (
            slots[1].resolved_entry.entrant.display_name
            if len(slots) > 1 and slots[1].resolved_entry_id
            else None
        ),
        "side_one_score": match.side_one_score,
        "side_two_score": match.side_two_score,
        "winner": match.winner.entrant.display_name if match.winner_id else None,
    }


def _descendant_matches(match: Match) -> list[Match]:
    found: dict[int, Match] = {}
    queue = deque([match.pk])
    while queue:
        source_id = queue.popleft()
        dependants = Match.objects.filter(slots__source_match_id=source_id).distinct()
        for dependant in dependants:
            if dependant.pk not in found:
                found[dependant.pk] = dependant
                queue.append(dependant.pk)
    return sorted(found.values(), key=lambda item: (item.round.number, item.number))


def _correction_payload(
    match: Match,
    *,
    competition_revision: int,
    outcome: str,
    side_one_score: int | None,
    side_two_score: int | None,
    winner_position: int | None,
) -> tuple[dict, StageEntry | None, list[Match]]:
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
    affected = _descendant_matches(match) if winner != match.winner else []
    payload = {
        "competition_id": match.round.draw.stage.competition_id,
        "revision": competition_revision,
        "match_id": match.pk,
        "outcome": outcome,
        "side_one_score": side_one_score,
        "side_two_score": side_two_score,
        "winner_entry_id": winner.pk if winner else None,
        "affected_match_ids": [item.pk for item in affected],
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
    }


def _load_correction_token(token: str) -> dict:
    try:
        return signing.loads(token, salt=CORRECTION_SALT, max_age=3600)
    except signing.BadSignature as error:
        raise ValidationError("The correction preview is invalid or expired.") from error


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
    return _correction_preview_response(
        match, current, winner, affected, token=token
    )


def apply_correction(*, actor, token: str, internal_reason: str) -> Match:
    require_organizer(actor, "competitions.change_match")
    require_organizer(actor, "competitions.change_competition")
    if not internal_reason.strip():
        raise ValidationError("An internal correction reason is required.")
    submitted = _load_correction_token(token)
    with transaction.atomic():
        competition, match = _lock_match(submitted["match_id"])
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
            MatchSlot.objects.filter(
                source_match_id__in=[match.pk, *affected_ids]
            ).update(is_resolved=False, resolved_entry=None)
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
            },
            public_data={
                "kind": "result_corrected",
                "match_id": match.pk,
                "match_code": match.code,
                "before": before,
                "after": _match_snapshot(match),
                "reset_matches": reset_snapshots,
            },
        )
        return match
