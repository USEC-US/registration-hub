"""Swiss setup commands inside the shared competition lock and revision boundary."""

from collections.abc import Sequence
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from config.organizers import require_organizer
from .command_support import (
    MAX_ENTRANTS,
    _check_revision,
    _lock_competition,
    _record_change,
    _validate_series_length,
    _validate_stage_sequence,
)
from .models import Stage
from .round_robin_commands import _points
from .stage_commands import _configured_incoming_count, _invalidate_drafts
from .swiss import TIEBREAKS, resolve_round_limit


def _swiss_rules(
    *,
    format,
    series_mode,
    length,
    round_count,
    win_target,
    loss_limit,
    advancement_count,
    points,
    tiebreaks,
    incoming_count=None,
):
    _validate_series_length(series_mode, length)
    _points(*points)
    if (
        not isinstance(tiebreaks, (list, tuple))
        or any(not isinstance(rule, str) or rule not in TIEBREAKS for rule in tiebreaks)
        or len(tiebreaks) != len(set(tiebreaks))
    ):
        raise ValidationError("Choose each supported Swiss tiebreaker at most once.")
    if format == Stage.Format.SWISS_FIXED:
        if type(advancement_count) is not int or not 2 <= advancement_count <= (
            incoming_count or MAX_ENTRANTS
        ):
            raise ValidationError(
                "Fixed Swiss requires a Top-N quota between 2 and the field size."
            )
    elif format == Stage.Format.SWISS_THRESHOLD:
        if advancement_count is not None or series_mode != Stage.SeriesMode.BEST_OF:
            raise ValidationError(
                "Threshold Swiss requires best-of matches and no Top-N quota."
            )
    try:
        limit = resolve_round_limit(
            incoming_count if incoming_count is not None else MAX_ENTRANTS,
            format=format,
            round_count=round_count,
            win_target=win_target,
            loss_limit=loss_limit,
        )
        return limit if incoming_count is not None else None
    except ValueError as error:
        raise ValidationError(str(error)) from error


def configure_swiss(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    stage_sequence: int = 1,
    name: str,
    format: str,
    series_mode: str,
    default_series_length: int,
    round_count: int | None,
    win_target: int | None,
    loss_limit: int | None,
    advancement_count: int | None,
    win_points: Decimal,
    draw_points: Decimal,
    loss_points: Decimal,
    tiebreaks: Sequence[str],
) -> Stage:
    require_organizer(actor, "competitions.change_competition")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValidationError({"name": "Enter a stage name of at most 100 characters."})
    points = _points(win_points, draw_points, loss_points)
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        _validate_stage_sequence(competition, stage_sequence)
        incoming = _configured_incoming_count(competition, stage_sequence)
        # Private setup may precede entrant selection or a successor stage.
        _swiss_rules(
            format=format,
            series_mode=series_mode,
            length=default_series_length,
            round_count=round_count,
            win_target=win_target,
            loss_limit=loss_limit,
            advancement_count=advancement_count,
            points=points,
            tiebreaks=tiebreaks,
            incoming_count=incoming if incoming else None,
        )
        stage = (
            Stage.objects.select_for_update()
            .filter(competition=competition, sequence=stage_sequence)
            .first()
        )
        values = dict(
            name=name.strip(),
            format=format,
            series_mode=series_mode,
            default_series_length=default_series_length,
            grand_final_policy="",
            swiss_round_count=round_count,
            swiss_win_target=win_target,
            swiss_loss_limit=loss_limit,
            advancement_count=advancement_count,
            win_points=points[0],
            draw_points=points[1],
            loss_points=points[2],
            tiebreaks=list(tiebreaks),
        )
        if stage:
            if stage.format != format:
                stage.group_plans.all().delete()
            for key, value in values.items():
                setattr(stage, key, value)
            stage.save(update_fields=tuple(values))
        else:
            stage = Stage.objects.create(
                competition=competition, sequence=stage_sequence, **values
            )
        _invalidate_drafts(stage)
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
