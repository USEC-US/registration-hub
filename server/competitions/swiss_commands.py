"""Swiss setup commands inside the shared competition lock and revision boundary."""

import hashlib
import json
import secrets
from collections.abc import Sequence
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from config.organizers import require_organizer
from .command_support import (
    MAX_ENTRANTS,
    MAX_MATCHES,
    _persist_stage_draw,
    _stage_for_command,
    _check_revision,
    _lock_competition,
    _record_change,
    _validate_series_length,
    _validate_stage_sequence,
)
from .models import (
    CompetitionEntrant,
    Match,
    MatchSlot,
    Round,
    Stage,
    StageDraw,
    TieResolution,
)
from .round_robin_commands import _points
from .stage_commands import _configured_incoming_count, _invalidate_drafts
from .swiss import (
    TIEBREAKS,
    SwissPairing,
    SwissResult,
    SwissStanding,
    pair_swiss_round,
    rank_swiss,
    resolve_round_limit,
)
from registrations.models import Registration


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


def _is_swiss(stage):
    return stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)


def _swiss_matches(draw, *, before_number=None, projected_matches=None):
    """A supplied sequence is the complete current fixture set, including result edits."""
    if projected_matches is not None:
        return sorted(
            (
                m
                for m in projected_matches
                if m.round.draw_id == draw.pk
                and m.round.state == Round.State.PUBLISHED
                and m.round.section == Round.Section.NORMAL
                and (before_number is None or m.round.number < before_number)
            ),
            key=lambda m: (m.round.number, m.number, m.pk),
        )
    queryset = Match.objects.filter(
        round__draw=draw,
        round__draw__state=StageDraw.State.PUBLISHED,
        round__state=Round.State.PUBLISHED,
        round__section=Round.Section.NORMAL,
    )
    if before_number is not None:
        queryset = queryset.filter(round__number__lt=before_number)
    matches = list(
        queryset.select_related("round")
        .prefetch_related("slots")
        .order_by("round__number", "number", "pk")
    )
    return matches


def _swiss_results(draw, *, before_number=None, projected_matches=None):
    """Confirmed current ordinary results only; forfeits never invent game metrics."""
    results = []
    for match in _swiss_matches(
        draw, before_number=before_number, projected_matches=projected_matches
    ):
        if match.status != Match.Status.FINAL:
            continue
        slots = sorted(match.slots.all(), key=lambda s: s.position)
        if len(slots) != 2 or not all(s.is_resolved for s in slots):
            raise ValidationError("The confirmed Swiss result has incomplete slots.")
        results.append(
            SwissResult(
                match.pk,
                match.round.number,
                slots[0].resolved_entry_id,
                slots[1].resolved_entry_id,
                match.outcome,
                match.side_one_score if match.outcome == Match.Outcome.PLAYED else None,
                match.side_two_score if match.outcome == Match.Outcome.PLAYED else None,
                match.winner_id,
            )
        )
    return results


def _rank(draw, results):
    stage = draw.stage
    try:
        return rank_swiss(
            dict(draw.entries.values_list("pk", "seed")),
            results,
            format=stage.format,
            points=(stage.win_points, stage.draw_points, stage.loss_points),
            tiebreaks=stage.tiebreaks,
            win_target=stage.swiss_win_target,
            loss_limit=stage.swiss_loss_limit,
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


def swiss_standings(
    draw: StageDraw, *, projected_matches: Sequence[Match] | None = None
) -> list[SwissStanding]:
    """Current ordinary standings; a supplied projection replaces the full fixture set."""
    return _rank(draw, _swiss_results(draw, projected_matches=projected_matches))


def _swiss_source_fingerprint(draw, number, *, projected_matches=None):
    """Stage-local rules, seeds/eligibility and earlier current results; no provenance."""
    stage = draw.stage
    entries = list(
        draw.entries.select_related("entrant__registration").order_by("seed", "pk")
    )
    game_metrics = bool(set(stage.tiebreaks) & {"GAME_DIFFERENCE", "GAMES_WON"})
    results = _swiss_results(
        draw, before_number=number, projected_matches=projected_matches
    )
    payload = [
        [
            stage.pk,
            stage.name,
            stage.format,
            stage.series_mode,
            stage.default_series_length,
            stage.swiss_round_count,
            stage.swiss_win_target,
            stage.swiss_loss_limit,
            draw.swiss_round_limit,
            stage.advancement_count,
            *[
                str(v.normalize())
                for v in (stage.win_points, stage.draw_points, stage.loss_points)
            ],
            stage.tiebreaks,
        ],
        [draw.pk, number],
        [
            [
                e.pk,
                e.seed,
                e.entrant_id,
                e.entrant.competition_id,
                e.entrant.status,
                e.entrant.is_selected,
                e.entrant.registration_id,
                e.entrant.registration.status,
                e.entrant.registration.tournament_game_id,
            ]
            for e in entries
        ],
        [
            [
                r.match_id,
                r.round_number,
                r.side_one_id,
                r.side_two_id,
                r.outcome,
                r.winner_id,
                r.side_one_score if game_metrics else None,
                r.side_two_score if game_metrics else None,
            ]
            for r in results
        ],
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode()
    ).hexdigest()


def _validate_swiss_field(draw):
    from .stage_commands import validate_stage_field

    stage = draw.stage
    if not _is_swiss(stage):
        raise ValidationError("Choose a Swiss stage.")
    entries = list(
        draw.entries.select_related("entrant__registration").order_by("seed")
    )
    validate_stage_field(stage, len(entries))
    limit = resolve_round_limit(
        len(entries),
        format=stage.format,
        round_count=stage.swiss_round_count,
        win_target=stage.swiss_win_target,
        loss_limit=stage.swiss_loss_limit,
    )
    if draw.swiss_round_limit != limit:
        raise ValidationError(
            "The saved Swiss round limit does not match the locked rules and actual field."
        )
    if [e.seed for e in entries] != list(range(1, len(entries) + 1)):
        raise ValidationError("The saved draw has invalid seeds.")
    if any(
        e.entrant.competition_id != stage.competition_id
        or e.entrant.status != CompetitionEntrant.Status.ACTIVE
        or e.entrant.registration.status != Registration.Status.APPROVED
        or e.entrant.registration.tournament_game_id
        != stage.competition.tournament_game_id
        for e in entries
    ):
        raise ValidationError(
            "Every Swiss entrant must still be active and approved for this division."
        )
    if stage.sequence == 1:
        selected = set(
            stage.competition.entrants.filter(
                is_selected=True, status=CompetitionEntrant.Status.ACTIVE
            ).values_list("pk", flat=True)
        )
        if (
            draw.source_draw_id
            or any(e.source_entry_id for e in entries)
            or {e.entrant_id for e in entries} != selected
        ):
            raise ValidationError(
                "The draw does not contain every selected entrant exactly once."
            )
    else:
        from .handoff_commands import validate_draw_source

        validate_draw_source(draw)
    if (
        Match.objects.filter(round__draw=draw)
        .exclude(round__section=Round.Section.TIEBREAK)
        .count()
        > MAX_MATCHES
    ):
        raise ValidationError("The ordinary-match storage budget is exhausted.")
    return entries


def _swiss_round_payload(round_):
    """Save this under private_data['swiss_round'] in the owning command's ChangeSet."""
    pairs, bye = [], None
    for match in round_.matches.prefetch_related("slots").order_by("number"):
        slots = sorted(match.slots.all(), key=lambda s: s.position)
        if len(slots) != 2:
            raise ValidationError("The saved Swiss round is incomplete.")
        if slots[1].entry_id is None:
            bye = slots[0].entry_id
        else:
            pairs.append([slots[0].entry_id, slots[1].entry_id])
    return {
        "round_id": round_.pk,
        "number": round_.number,
        "version": round_.version,
        "source_fingerprint": round_.source_fingerprint,
        "rematches_authorized": round_.rematches_authorized,
        "pairs": pairs,
        "bye_entry_id": bye,
    }


def validate_swiss_round(round_, *, verify_pairing=True):
    draw, stage = round_.draw, round_.draw.stage
    entries = _validate_swiss_field(draw)
    if (
        round_.state == Round.State.SUPERSEDED
        or round_.section != Round.Section.NORMAL
        or round_.group_id
        or round_.tie_resolution_id
        or not 1 <= round_.number <= draw.swiss_round_limit
    ):
        raise ValidationError(
            "Choose a current ordinary Swiss round within the saved limit."
        )
    prior = list(
        draw.rounds.filter(section=Round.Section.NORMAL, number__lt=round_.number)
        .exclude(state=Round.State.SUPERSEDED)
        .order_by("number")
    )
    if [r.number for r in prior] != list(range(1, round_.number)) or any(
        r.state != Round.State.PUBLISHED
        or r.matches.exclude(status=Match.Status.FINAL).exists()
        for r in prior
    ):
        raise ValidationError(
            "Finish every prior current Swiss round before generating or publishing another."
        )
    source = _swiss_source_fingerprint(draw, round_.number)
    if round_.source_fingerprint != source:
        raise ValidationError(
            "The saved Swiss round source changed. Regenerate the preview."
        )
    results = _swiss_results(draw, before_number=round_.number)
    rows = _rank(draw, results)
    active = {r.entry_id for r in rows if r.status == "ACTIVE"}
    matches = list(round_.matches.prefetch_related("slots").order_by("number"))
    if not active or [m.number for m in matches] != list(
        range(1, (len(active) + 1) // 2 + 1)
    ):
        raise ValidationError(
            "The saved Swiss round must cover every active entrant once."
        )
    appearances = []
    for match in matches:
        slots = sorted(match.slots.all(), key=lambda s: s.position)
        if [s.position for s in slots] != [1, 2] or slots[0].entry_id is None:
            raise ValidationError("The saved Swiss round has incomplete slots.")
        for slot in slots:
            if (
                slot.source_match_id
                or slot.source_outcome
                or not slot.is_resolved
                or slot.entry_id != slot.resolved_entry_id
                or slot.is_empty != (slot.entry_id is None)
            ):
                raise ValidationError("The saved Swiss round has invalid slot sources.")
            if slot.entry_id is not None:
                appearances.append(slot.entry_id)
        if stage.format == Stage.Format.SWISS_THRESHOLD:
            _validate_series_length(
                match.effective_series_mode, match.effective_series_length
            )
            if match.effective_series_mode != Stage.SeriesMode.BEST_OF:
                raise ValidationError(
                    "Threshold Swiss requires decisive best-of matches."
                )
        if round_.state == Round.State.DRAFT and (
            match.status != Match.Status.PENDING
            or match.outcome
            or match.winner_id
            or match.started_at
            or match.completed_at
            or match.side_one_score is not None
            or match.side_two_score is not None
        ):
            raise ValidationError(
                "A private Swiss preview cannot contain played results."
            )
    if len(appearances) != len(active) or set(appearances) != active:
        raise ValidationError(
            "The saved Swiss round must cover every active entrant once."
        )
    payload = _swiss_round_payload(round_)
    change = (
        stage.competition.changes.filter(private_data__swiss_round__round_id=round_.pk)
        .order_by("revision")
        .first()
    )
    if change is None or change.private_data["swiss_round"] != payload:
        raise ValidationError("The saved Swiss pairing or rematch intent changed.")
    if round_.rematches_authorized and not change.internal_reason.strip():
        raise ValidationError(
            "The saved rematch exception requires a recorded internal reason."
        )
    previous_pairs = {
        frozenset((r.side_one_id, r.side_two_id))
        for r in results
        if r.side_two_id is not None
    }
    if not round_.rematches_authorized and any(
        frozenset(p) in previous_pairs for p in payload["pairs"]
    ):
        raise ValidationError("The saved Swiss round contains an unauthorized rematch.")
    if verify_pairing:
        try:
            expected = pair_swiss_round(
                {e.pk: e.seed for e in entries},
                rows,
                results,
                format=stage.format,
                allow_rematches=round_.rematches_authorized,
            )
        except ValueError as error:
            raise ValidationError(str(error)) from error
        if (
            payload["pairs"] != [list(p) for p in expected.pairs]
            or payload["bye_entry_id"] != expected.bye_entry_id
        ):
            raise ValidationError(
                "The saved pairing does not match the confirmed Swiss policy."
            )


def validate_swiss_draw(draw):
    _validate_swiss_field(draw)
    rounds = list(
        draw.rounds.filter(section=Round.Section.NORMAL)
        .exclude(state=Round.State.SUPERSEDED)
        .order_by("number")
    )
    if not rounds or [r.number for r in rounds] != list(range(1, len(rounds) + 1)):
        raise ValidationError(
            "The saved Swiss draw must have contiguous current rounds."
        )
    drafts = [r for r in rounds if r.state == Round.State.DRAFT]
    if len(drafts) > 1 or (drafts and drafts[0].pk != rounds[-1].pk):
        raise ValidationError("Save only one private next Swiss round.")
    for round_ in rounds:
        validate_swiss_round(round_)


def _persist_swiss_round(
    draw: StageDraw,
    *,
    number: int,
    pairing: SwissPairing,
    source_fingerprint: str,
    rematches_authorized: bool,
) -> Round:
    count = len(pairing.pairs) + int(pairing.bye_entry_id is not None)
    existing = (
        Match.objects.filter(round__draw=draw)
        .exclude(round__section=Round.Section.TIEBREAK)
        .count()
    )
    if existing + count > MAX_MATCHES:
        raise ValidationError("The ordinary-match storage budget is exhausted.")
    version = (
        draw.rounds.filter(section=Round.Section.NORMAL, number=number)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    draw.rounds.filter(
        section=Round.Section.NORMAL, number=number, state=Round.State.DRAFT
    ).update(state=Round.State.SUPERSEDED)
    round_ = Round.objects.create(
        draw=draw,
        number=number,
        version=version,
        source_fingerprint=source_fingerprint,
        rematches_authorized=rematches_authorized,
    )
    ordinal = Match.objects.filter(round__draw=draw).count()
    pairs = list(pairing.pairs)
    if pairing.bye_entry_id is not None:
        pairs.append((pairing.bye_entry_id, None))
    for index, pair in enumerate(pairs, 1):
        match = Match.objects.create(
            round=round_, number=index, code=f"{draw.stage.name}-M{ordinal + index}"
        )
        MatchSlot.objects.bulk_create(
            [
                MatchSlot(
                    match=match,
                    position=position,
                    entry_id=entry_id,
                    resolved_entry_id=entry_id,
                    is_empty=entry_id is None,
                    is_resolved=True,
                )
                for position, entry_id in enumerate(pair, 1)
            ]
        )
    return round_


def _persist_swiss_fixtures(draw, entries):
    rows = swiss_standings(draw)
    pairing = pair_swiss_round(
        {e.pk: e.seed for e in entries}, rows, (), format=draw.stage.format
    )
    return _persist_swiss_round(
        draw,
        number=1,
        pairing=pairing,
        source_fingerprint=_swiss_source_fingerprint(draw, 1),
        rematches_authorized=False,
    )


def save_swiss_draw(
    *,
    actor,
    competition_id: int,
    expected_revision: int,
    ordered_entrant_ids: Sequence[int] | None = None,
    randomized: bool = False,
    stage_id: int | None = None,
) -> StageDraw:
    require_organizer(actor, "competitions.change_competition")
    if type(randomized) is not bool:
        raise ValidationError("Randomization must be an explicit boolean.")
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = _stage_for_command(competition, stage_id)
        if not _is_swiss(stage) or stage.sequence != 1:
            raise ValidationError(
                "Save first-stage Swiss seeds; later draws use qualified handoffs."
            )
        if stage.published_at:
            raise ValidationError("The published draw cannot be replaced directly.")
        entrants = list(
            competition.entrants.select_for_update()
            .filter(is_selected=True, status=CompetitionEntrant.Status.ACTIVE)
            .order_by("pk")
        )
        ids = [e.pk for e in entrants]
        if not 2 <= len(ids) <= MAX_ENTRANTS:
            raise ValidationError("Choose between 2 and 256 entrants.")
        if randomized:
            ordered = ids.copy()
            secrets.SystemRandom().shuffle(ordered)
        else:
            ordered = list(ordered_entrant_ids or ())
            if (
                any(type(i) is not int for i in ordered)
                or len(ordered) != len(set(ordered))
                or set(ordered) != set(ids)
            ):
                raise ValidationError("Manual seeds must include every entrant once.")
        registrations = list(
            Registration.objects.select_for_update()
            .filter(pk__in=[e.registration_id for e in entrants])
            .order_by("pk")
        )
        if len(registrations) != len(ids) or any(
            r.status != Registration.Status.APPROVED
            or r.tournament_game_id != competition.tournament_game_id
            for r in registrations
        ):
            raise ValidationError(
                "Every entrant must still be approved for this division."
            )
        draw = _persist_stage_draw(stage, ordered, randomized=randomized)
        _record_change(
            competition,
            actor=actor,
            kind="draw_saved",
            private_data={
                "draw_id": draw.pk,
                "entrant_order": ordered,
                "randomized": randomized,
                "swiss_round": _swiss_round_payload(draw.rounds.get()),
            },
        )
        return draw


def generate_swiss_round(
    *,
    actor,
    stage_id: int,
    expected_revision: int,
    regenerate: bool = False,
    allow_rematches: bool = False,
    internal_reason: str = "",
) -> Round:
    require_organizer(actor, "competitions.change_competition")
    if type(regenerate) is not bool or type(allow_rematches) is not bool:
        raise ValidationError(
            "Regeneration and rematch intent must be explicit booleans."
        )
    if not isinstance(internal_reason, str) or (
        allow_rematches and not internal_reason.strip()
    ):
        raise ValidationError(
            "A confirmed rematch exception requires a nonblank internal reason."
        )
    competition_id = Stage.objects.values_list("competition_id", flat=True).get(
        pk=stage_id
    )
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        stage = _stage_for_command(competition, stage_id)
        draw = (
            stage.draws.select_for_update()
            .filter(state=StageDraw.State.PUBLISHED)
            .first()
        )
        if draw is None or not _is_swiss(stage):
            raise ValidationError(
                "Publish this Swiss stage's first draw before generating a next round."
            )
        _validate_swiss_field(draw)
        published = list(
            draw.rounds.filter(
                state=Round.State.PUBLISHED, section=Round.Section.NORMAL
            ).order_by("number")
        )
        number = len(published) + 1
        if [r.number for r in published] != list(range(1, number)) or any(
            r.matches.exclude(status=Match.Status.FINAL).exists() for r in published
        ):
            raise ValidationError("Finish every prior current Swiss round first.")
        if stage.status == Stage.Status.COMPLETE or number > draw.swiss_round_limit:
            raise ValidationError(
                "This Swiss stage is not continuing within its saved round limit."
            )
        current = (
            draw.rounds.select_for_update()
            .filter(state=Round.State.DRAFT, section=Round.Section.NORMAL)
            .first()
        )
        if current and not regenerate:
            if current.number != number:
                raise ValidationError("The saved preview is not the next Swiss round.")
            validate_swiss_round(current, verify_pairing=False)
            return current
        results = _swiss_results(draw)
        rows = _rank(draw, results)
        try:
            pairing = pair_swiss_round(
                dict(draw.entries.values_list("pk", "seed")),
                rows,
                results,
                format=stage.format,
                allow_rematches=allow_rematches,
            )
        except ValueError as error:
            raise ValidationError(str(error)) from error
        round_ = _persist_swiss_round(
            draw,
            number=number,
            pairing=pairing,
            source_fingerprint=_swiss_source_fingerprint(draw, number),
            rematches_authorized=allow_rematches,
        )
        _record_change(
            competition,
            actor=actor,
            kind="swiss_round_saved",
            internal_reason=internal_reason,
            private_data={
                "draw_id": draw.pk,
                "stage_id": stage.pk,
                "regenerated": regenerate,
                "swiss_round": _swiss_round_payload(round_),
                "repeat_pairs": [list(p) for p in pairing.repeat_pairs],
                "cross_group_pairs": [list(p) for p in pairing.cross_group_pairs],
            },
        )
        return round_


def _swiss_public_round(round_):
    from .command_support import _match_snapshot

    return {
        "round_id": round_.pk,
        "round_number": round_.number,
        "automatic_results": [
            _match_snapshot(m)
            for m in round_.matches.filter(outcome=Match.Outcome.BYE).select_related(
                "winner__entrant"
            )
        ],
    }


def publish_swiss_round(*, actor, round_id: int, expected_revision: int) -> Round:
    require_organizer(actor, "competitions.change_competition")
    competition_id = Round.objects.values_list(
        "draw__stage__competition_id", flat=True
    ).get(pk=round_id)
    with transaction.atomic():
        competition = _lock_competition(competition_id)
        _check_revision(competition, expected_revision)
        round_ = (
            Round.objects.select_for_update()
            .select_related("draw__stage__competition")
            .get(pk=round_id)
        )
        if (
            round_.draw.state != StageDraw.State.PUBLISHED
            or round_.state != Round.State.DRAFT
        ):
            raise ValidationError(
                "Choose a saved private round of a current published Swiss draw."
            )
        list(Match.objects.select_for_update().filter(round=round_))
        list(MatchSlot.objects.select_for_update().filter(match__round=round_))
        list(
            Registration.objects.select_for_update().filter(
                pk__in=round_.draw.entries.values_list(
                    "entrant__registration_id", flat=True
                )
            )
        )
        validate_swiss_draw(round_.draw)
        round_.state = Round.State.PUBLISHED
        round_.published_at = timezone.now()
        round_.save(update_fields=("state", "published_at"))
        from .commands import _resolve_automatic_matches

        _resolve_automatic_matches(round_.draw)
        update_swiss_completion(round_.draw.stage, round_.draw)
        _record_change(
            competition,
            actor=actor,
            kind="swiss_round_published",
            private_data={"round_id": round_.pk},
            public_data={
                "kind": "swiss_round_published",
                "stage_id": round_.draw.stage_id,
                **_swiss_public_round(round_),
            },
        )
        return round_


def update_swiss_completion(stage: Stage, draw: StageDraw) -> None:
    from .qualification import stage_qualification

    qualification = stage_qualification(draw)
    now = timezone.now()
    for resolution_id, status in qualification["resolution_states"].items():
        TieResolution.objects.filter(pk=resolution_id).update(
            state=status,
            confirmed_at=now if status == TieResolution.State.CONFIRMED else None,
        )
    state = qualification["qualification_state"]
    stage.status = (
        Stage.Status.COMPLETE
        if state == "RESOLVED"
        else Stage.Status.AWAITING
        if state in ("AWAITING_RESOLUTION", "BLOCKED")
        else Stage.Status.IN_PROGRESS
        if any(m.started_at for m in _swiss_matches(draw))
        else Stage.Status.READY
    )
    stage.champion = None
    stage.completed_without_champion = False
    stage.completed_at = (stage.completed_at or now) if state == "RESOLVED" else None
    stage.save(
        update_fields=(
            "status",
            "champion",
            "completed_without_champion",
            "completed_at",
        )
    )
