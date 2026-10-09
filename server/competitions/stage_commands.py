"""Locked edits and validation of the ordered competition plan."""

from collections.abc import Sequence

from django.core.exceptions import ValidationError
from django.db import transaction

from config.organizers import require_organizer
from .command_support import (
    MAX_ENTRANTS,
    MAX_MATCHES,
    _check_revision,
    _lock_competition,
    _record_change,
    _require_plan_editable,
)
from .models import Stage, StageDraw, StageGroupPlan


def _locked_stage(stage_id, revision):
    competition_id = Stage.objects.values_list("competition_id", flat=True).get(
        pk=stage_id
    )
    competition = _lock_competition(competition_id)
    _check_revision(competition, revision)
    _require_plan_editable(competition)
    return competition, Stage.objects.select_for_update().get(pk=stage_id)


def _invalidate_drafts(stage):
    StageDraw.objects.filter(
        stage__competition=stage.competition,
        stage__sequence__gte=stage.sequence,
        state="DRAFT",
    ).update(state="SUPERSEDED")


def set_stage_advancement(
    *, actor, stage_id: int, expected_revision: int, advancement_count: int | None
) -> Stage:
    require_organizer(actor, "competitions.change_competition")
    if advancement_count is not None and (
        type(advancement_count) is not int or not 1 <= advancement_count <= MAX_ENTRANTS
    ):
        raise ValidationError("Advancement count must be an integer between 1 and 256.")
    with transaction.atomic():
        competition, stage = _locked_stage(stage_id, expected_revision)
        if stage.format not in (
            Stage.Format.SINGLE_ELIMINATION,
            Stage.Format.DOUBLE_ELIMINATION,
        ):
            raise ValidationError("Round Robin advancement is configured per group.")
        stage.advancement_count = advancement_count
        stage.save(update_fields=("advancement_count",))
        _invalidate_drafts(stage)
        _record_change(
            competition,
            actor=actor,
            kind="stage_advancement_set",
            private_data={"stage_id": stage.pk, "advancement_count": advancement_count},
        )
        return stage


def set_stage_groups(
    *,
    actor,
    stage_id: int,
    expected_revision: int,
    group_specs: Sequence[tuple[str, int, int]],
) -> list[StageGroupPlan]:
    require_organizer(actor, "competitions.change_competition")
    try:
        specs = [(name.strip(), size, quota) for name, size, quota in group_specs]
        if (
            not specs
            or len({name for name, _, _ in specs}) != len(specs)
            or any(
                not 1 <= len(name) <= 100
                or type(size) is not int
                or not 2 <= size <= MAX_ENTRANTS
                or type(quota) is not int
                or not 1 <= quota <= size
                for name, size, quota in specs
            )
            or sum(size for _, size, _ in specs) > MAX_ENTRANTS
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(
            "Use unique named groups, integer sizes of at least two, and quotas between one and group size."
        ) from error
    with transaction.atomic():
        competition, stage = _locked_stage(stage_id, expected_revision)
        if stage.format != Stage.Format.ROUND_ROBIN:
            raise ValidationError("Group plans require a Round Robin stage.")
        stage.group_plans.all().delete()
        plans = StageGroupPlan.objects.bulk_create(
            [
                StageGroupPlan(
                    stage=stage, number=i, name=name, size=size, qualifying_places=quota
                )
                for i, (name, size, quota) in enumerate(specs, 1)
            ]
        )
        _invalidate_drafts(stage)
        _record_change(
            competition,
            actor=actor,
            kind="stage_groups_set",
            private_data={"stage_id": stage.pk, "groups": specs},
        )
        return plans


def _resequence(stages):
    used = {stage.sequence for stage in stages}
    spare = next((i for i in range(1, 32768) if i not in used), None)
    if spare is None:
        raise ValidationError("No spare stage position is available for reordering.")
    for target, stage in enumerate(stages, 1):
        if stage.sequence == target:
            continue
        occupant = next((s for s in stages if s.sequence == target), None)
        previous = stage.sequence
        if occupant:
            occupant.sequence = spare
            occupant.save(update_fields=("sequence",))
        stage.sequence = target
        stage.save(update_fields=("sequence",))
        if occupant:
            occupant.sequence = previous
            occupant.save(update_fields=("sequence",))


def reorder_stages(
    *, actor, competition_id: int, expected_revision: int, stage_ids: Sequence[int]
) -> list[Stage]:
    require_organizer(actor, "competitions.change_competition")
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        _require_plan_editable(competition)
        stages = {s.pk: s for s in competition.stages.select_for_update()}
        if len(stage_ids) != len(stages) or set(stage_ids) != set(stages):
            raise ValidationError("Include every stage exactly once.")
        ordered = [stages[i] for i in stage_ids]
        StageDraw.objects.filter(stage__competition=competition, state="DRAFT").update(
            state="SUPERSEDED"
        )
        _resequence(ordered)
        _record_change(
            competition,
            actor=actor,
            kind="stages_reordered",
            private_data={"stage_ids": list(stage_ids)},
        )
        return ordered


def remove_stage(*, actor, stage_id: int, expected_revision: int) -> None:
    require_organizer(actor, "competitions.change_competition")
    with transaction.atomic():
        competition, stage = _locked_stage(stage_id, expected_revision)
        if stage.draws.exists():
            raise ValidationError("A stage with retained draws cannot be removed.")
        snapshot = {
            "stage_id": stage.pk,
            "sequence": stage.sequence,
            "name": stage.name,
            "format": stage.format,
        }
        stage.delete()
        _resequence(list(competition.stages.select_for_update()))
        _record_change(
            competition, actor=actor, kind="stage_removed", private_data=snapshot
        )


def validate_stage_plan(competition) -> list[dict]:
    from .commands import _generate_elimination, _validate_elimination_setup
    from .round_robin_commands import _rules

    stages = list(competition.stages.prefetch_related("group_plans"))
    incoming = competition.entrants.filter(is_selected=True, status="ACTIVE").count()
    rows = []
    if not stages or [s.sequence for s in stages] != list(range(1, len(stages) + 1)):
        raise ValidationError("Configure a contiguous ordered stage plan.")
    for index, stage in enumerate(stages):
        if not 2 <= incoming <= MAX_ENTRANTS:
            raise ValidationError(
                f"{stage.name} requires between 2 and 256 eligible entrants; the plan supplies {incoming}."
            )
        final = index == len(stages) - 1
        if stage.format == Stage.Format.ROUND_ROBIN:
            _rules(
                stage.round_robin_meetings,
                stage.series_mode,
                stage.default_series_length,
                (stage.win_points, stage.draw_points, stage.loss_points),
                stage.tiebreaks,
            )
            plans = list(stage.group_plans.all())
            if not plans or sum(p.size for p in plans) != incoming:
                raise ValidationError(
                    f"{stage.name}: group sizes must total the incoming field of {incoming}."
                )
            outgoing = sum(p.qualifying_places for p in plans)
            count = stage.round_robin_meetings * sum(
                p.size * (p.size - 1) // 2 for p in plans
            )
        else:
            _validate_elimination_setup(stage.format, stage.grand_final_policy)
            outgoing = stage.advancement_count
            if final and outgoing is not None:
                raise ValidationError(
                    f"{stage.name}: the final elimination stage has no outgoing quota."
                )
            if not final and (
                type(outgoing) is not int or not 1 <= outgoing <= incoming
            ):
                raise ValidationError(
                    f"{stage.name}: set an advancement count between 1 and {incoming}."
                )
            count = sum(len(r.matches) for r in _generate_elimination(stage, incoming))
        if count > MAX_MATCHES:
            raise ValidationError(
                f"{stage.name}: the generated draw exceeds the match limit."
            )
        rows.append(
            {
                "stage_id": stage.pk,
                "incoming_count": incoming,
                "outgoing_count": None if final else outgoing,
                "ordinary_match_count": count,
            }
        )
        incoming = outgoing
    return rows
