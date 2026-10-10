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
    _supersede_draws,
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
    _supersede_draws(
        StageDraw.objects.filter(
            stage__competition=stage.competition,
            stage__sequence__gte=stage.sequence,
            state="DRAFT",
        )
    )


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
            raise ValidationError(
                "Use the format-specific configuration for this stage’s advancement."
            )
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
    group_specs: Sequence[tuple[str, int | None, int]],
) -> list[StageGroupPlan]:
    require_organizer(actor, "competitions.change_competition")
    specs = _validate_group_specs(group_specs)
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
        _require_swiss_successor(ordered)
        _supersede_draws(
            StageDraw.objects.filter(stage__competition=competition, state="DRAFT")
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
        _require_swiss_successor(list(competition.stages.exclude(pk=stage.pk)))
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


def _validate_group_specs(group_specs):
    try:
        specs = [(name.strip(), size, quota) for name, size, quota in group_specs]
        if (
            not specs
            or len({name for name, _, _ in specs}) != len(specs)
            or any(
                not 1 <= len(name) <= 100
                or (
                    size is not None
                    and (type(size) is not int or not 2 <= size <= MAX_ENTRANTS)
                )
                or type(quota) is not int
                or not 1 <= quota <= (size if size is not None else MAX_ENTRANTS)
                for name, size, quota in specs
            )
            or len({size is None for _, size, _ in specs}) != 1
            or sum(
                size if size is not None else max(2, quota) for _, size, quota in specs
            )
            > MAX_ENTRANTS
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(
            "Use unique named groups with either all exact or all automatic sizes and valid integer quotas."
        ) from error
    return specs


def resolve_group_sizes(
    group_specs: Sequence[tuple[str, int | None, int]], incoming_count: int
) -> list[int]:
    specs = _validate_group_specs(group_specs)
    if type(incoming_count) is not int or not 2 <= incoming_count <= MAX_ENTRANTS:
        raise ValidationError("A group field requires between 2 and 256 entrants.")
    if specs[0][1] is not None:
        sizes = [size for _, size, _ in specs]
        if sum(sizes) != incoming_count:
            raise ValidationError("Exact group sizes must total the incoming field.")
        return sizes
    sizes = [max(2, quota) for _, _, quota in specs]
    if sum(sizes) > incoming_count:
        raise ValidationError("The incoming field cannot fill every group and quota.")
    for _ in range(incoming_count - sum(sizes)):
        smallest = min(range(len(sizes)), key=sizes.__getitem__)
        sizes[smallest] += 1
    return sizes


def _require_swiss_successor(stages):
    if stages and stages[-1].format in (
        Stage.Format.SWISS_FIXED,
        Stage.Format.SWISS_THRESHOLD,
    ):
        raise ValidationError(
            "A Swiss stage must have a successor; it cannot be the final stage."
        )


def _configured_incoming_count(competition, sequence):
    incoming = competition.entrants.filter(is_selected=True, status="ACTIVE").count()
    for previous in competition.stages.filter(sequence__lt=sequence).prefetch_related(
        "group_plans"
    ):
        if previous.format == Stage.Format.ROUND_ROBIN:
            plans = list(previous.group_plans.all())
            incoming = sum(p.qualifying_places for p in plans) if plans else None
        elif previous.format == Stage.Format.SWISS_THRESHOLD:
            incoming = None
        else:
            incoming = previous.advancement_count
    return incoming


def validate_stage_field(
    stage, incoming_count: int | None
) -> tuple[int | None, int | None]:
    """Validate locked rules; resolve feasibility only for a concrete field."""
    from .commands import _generate_elimination, _validate_elimination_setup
    from .command_support import _validate_best_of
    from .round_robin_commands import _rules
    from .swiss_commands import _swiss_rules

    if incoming_count is not None and (
        type(incoming_count) is not int or not 2 <= incoming_count <= MAX_ENTRANTS
    ):
        raise ValidationError(
            f"{stage.name} requires between 2 and 256 eligible entrants."
        )
    if stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
        limit = _swiss_rules(
            format=stage.format,
            series_mode=stage.series_mode,
            length=stage.default_series_length,
            round_count=stage.swiss_round_count,
            win_target=stage.swiss_win_target,
            loss_limit=stage.swiss_loss_limit,
            advancement_count=stage.advancement_count,
            points=(stage.win_points, stage.draw_points, stage.loss_points),
            tiebreaks=stage.tiebreaks,
            incoming_count=incoming_count,
        )
        outgoing = stage.advancement_count
        count = None if incoming_count is None else ((incoming_count + 1) // 2) * limit
    elif stage.format == Stage.Format.ROUND_ROBIN:
        _rules(
            stage.round_robin_meetings,
            stage.series_mode,
            stage.default_series_length,
            (stage.win_points, stage.draw_points, stage.loss_points),
            stage.tiebreaks,
        )
        specs = _validate_group_specs(
            [(p.name, p.size, p.qualifying_places) for p in stage.group_plans.all()]
        )
        outgoing = sum(quota for _, _, quota in specs)
        count = None
        if incoming_count is not None:
            sizes = resolve_group_sizes(specs, incoming_count)
            count = stage.round_robin_meetings * sum(
                size * (size - 1) // 2 for size in sizes
            )
    else:
        _validate_elimination_setup(stage.format, stage.grand_final_policy)
        _validate_best_of(stage.default_series_length)
        outgoing = stage.advancement_count
        if outgoing is not None and (
            type(outgoing) is not int
            or not 1 <= outgoing <= (incoming_count or MAX_ENTRANTS)
        ):
            raise ValidationError(
                f"{stage.name}: set a valid advancement count for this field."
            )
        count = (
            None
            if incoming_count is None
            else sum(
                len(r.matches) for r in _generate_elimination(stage, incoming_count)
            )
        )
    if count is not None and count > MAX_MATCHES:
        raise ValidationError(
            f"{stage.name}: the generated draw exceeds the match limit."
        )
    return outgoing, count


def validate_stage_plan(competition) -> list[dict]:
    stages = list(competition.stages.prefetch_related("group_plans"))
    incoming = competition.entrants.filter(is_selected=True, status="ACTIVE").count()
    rows = []
    if not stages or [s.sequence for s in stages] != list(range(1, len(stages) + 1)):
        raise ValidationError("Configure a contiguous ordered stage plan.")
    _require_swiss_successor(stages)
    for index, stage in enumerate(stages):
        final = index == len(stages) - 1
        outgoing, count = validate_stage_field(stage, incoming)
        if stage.format in (
            Stage.Format.SINGLE_ELIMINATION,
            Stage.Format.DOUBLE_ELIMINATION,
        ):
            if final and outgoing is not None:
                raise ValidationError(
                    f"{stage.name}: the final elimination stage has no outgoing quota."
                )
            if not final and outgoing is None:
                raise ValidationError(f"{stage.name}: set an advancement count.")
        rows.append(
            {
                "stage_id": stage.pk,
                "incoming_count": incoming,
                "outgoing_count": None if final else outgoing,
                "ordinary_match_count": count,
                "requires_actual_field_validation": incoming is None,
            }
        )
        incoming = outgoing
    return rows
