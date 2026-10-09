from django.core.exceptions import ValidationError
from tournaments.models import TournamentGame
from .models import ChangeSet, Competition, Match, Stage

MAX_ENTRANTS = 256
MAX_MATCHES = 16_384


def _lock_competition(competition_id: int) -> Competition:
    division_id = Competition.objects.values_list("tournament_game_id", flat=True).get(
        pk=competition_id
    )
    # ponytail: one division lock serializes competition and registration writes;
    # use finer locks only if measured event throughput requires them.
    TournamentGame.objects.select_for_update().get(pk=division_id)
    return (
        Competition.objects.select_for_update()
        .select_related(
            "tournament_game", "tournament_game__tournament", "tournament_game__game"
        )
        .get(pk=competition_id)
    )


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


def _validate_best_of(length: int) -> None:
    _validate_series_length(Stage.SeriesMode.BEST_OF, length)


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
        "applied_series_length": match.applied_series_length,
        "applied_series_mode": match.applied_series_mode,
        "started_at": match.started_at.isoformat() if match.started_at else None,
        "completed_at": match.completed_at.isoformat() if match.completed_at else None,
    }


def _validate_series_length(mode: str, length: int) -> None:
    if type(length) is not int or not 1 <= length <= 32767:
        raise ValidationError("Series length must be an integer between 1 and 32767.")
    if mode == Stage.SeriesMode.BEST_OF:
        if length % 2 == 0:
            raise ValidationError("Best-of length must be a positive odd number.")
    elif mode != Stage.SeriesMode.FIXED_GAMES:
        raise ValidationError("Choose a supported series mode.")


def _stage_for_command(competition, stage_id=None):
    stage = (
        Stage.objects.select_for_update()
        .filter(
            competition=competition,
            **({"sequence": 1} if stage_id is None else {"pk": stage_id}),
        )
        .first()
    )
    if stage is None:
        raise ValidationError("Configure a stage belonging to this competition.")
    return stage


def _require_plan_editable(competition):
    if competition.stages.filter(sequence=1, published_at__isnull=False).exists():
        raise ValidationError("The whole stage plan is locked after first publication.")


def _validate_stage_sequence(competition, sequence):
    _require_plan_editable(competition)
    if type(sequence) is not int or not 1 <= sequence <= min(
        32767, competition.stages.count() + 1
    ):
        raise ValidationError(
            "Configure an existing stage or the next contiguous stage."
        )
