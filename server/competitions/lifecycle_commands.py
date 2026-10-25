"""Signed entrant transitions; projections are read-only and applies own the transaction."""

import json
from copy import copy

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from config.organizers import require_organizer
from .command_support import (
    _check_revision,
    _lock_competition,
    _match_snapshot,
    _record_change,
    _supersede_draws,
    _supersede_ties,
)
from .models import (
    Competition,
    CompetitionEntrant,
    Match,
    MatchSlot,
    Round,
    Stage,
    StageDraw,
    TieResolution,
)
from .result_projection import (
    COMPETITIVE_FIELDS,
    _ordered_matches,
    _routed_entry_id,
    project_elimination_results,
    apply_elimination_projection,
)
from .qualification import stage_qualification, projected_fixture_matches
from .handoff_commands import project_handoff_corrections, apply_handoff_impact
from .swiss_corrections import project_swiss_correction, apply_swiss_correction

LIFECYCLE_SALT = "competitions.lifecycle"
ELIMINATION = (Stage.Format.SINGLE_ELIMINATION, Stage.Format.DOUBLE_ELIMINATION)
SWISS = (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)


def _json(value):
    return json.loads(json.dumps(value, default=lambda v: v.isoformat()))


def _state(match):
    return {
        **{f: getattr(match, f) for f in COMPETITIVE_FIELDS},
        "slots": list(
            match.slots.order_by("position").values_list(
                "is_resolved", "resolved_entry_id"
            )
        ),
    }


def _decode_state(value):
    result = dict(value)
    for field in ("started_at", "completed_at"):
        if result[field] is not None:
            result[field] = parse_datetime(result[field])
    return result


def _authoritative(match):
    effect = match.removal_effect
    return bool(
        effect
        and effect.get("active")
        and effect.get("applied") == _json(_state(match))
    )


def invalidate_removal_effect(match):
    """Competitive organizer corrections supersede automatic authority, not its history."""
    if match.removal_effect:
        match.removal_effect = {**match.removal_effect, "active": False}
        match.save(update_fields=["removal_effect"])


def project_removal_results(
    draw, *, entrant_statuses=None, restore_change_id=None, result_updates=None
):
    result_updates = result_updates or {}
    statuses = entrant_statuses or {}
    matches = _ordered_matches(draw, include_drafts=False)
    entries = {e.pk: e for e in draw.entries.select_related("entrant")}
    unavailable = {
        pk: e.entrant_id
        for pk, e in entries.items()
        if statuses.get(e.entrant_id, e.entrant.status) != "ACTIVE"
    }
    baselines, preserved = {}, []
    for match in matches:
        effect = match.removal_effect
        relevant = effect and (
            restore_change_id is None
            or restore_change_id in effect.get("causes", {}).values()
        )
        if relevant and _authoritative(match) and match.pk not in result_updates:
            baseline = _decode_state(effect["before"])
            baselines[match.pk] = baseline
        elif relevant and restore_change_id is not None:
            preserved.append(match.pk)
    if draw.stage.format in ELIMINATION:
        projection = project_elimination_results(
            draw,
            result_updates=result_updates,
            entrant_statuses=statuses,
            restoration_states=baselines,
        )
        baselines = projection["restoration_states"]
    else:
        states, changed, impacts = {}, [], []
        for match in matches:
            state = dict(baselines.get(match.pk, _state(match)))
            slots = state["slots"]
            if state["status"] in ("PENDING", "LIVE") and all(r for r, _ in slots):
                real = [e for _, e in slots if e is not None]
                active = [e for e in real if e not in unavailable]
                if len(real) == 2 and len(active) < 2:
                    state.update(
                        status="FINAL",
                        outcome="FORFEIT" if active else "DOUBLE_FORFEIT",
                        winner_id=active[0] if active else None,
                        completed_at=None,
                    )
            states[match.pk] = state
            if _json(state) != _json(_state(match)):
                changed.append(match.pk)
                projected = copy(match)
                for f in COMPETITIVE_FIELDS:
                    setattr(projected, f, state[f])
                impacts.append(
                    {
                        "match_id": match.pk,
                        "before": _match_snapshot(match),
                        "after": _match_snapshot(projected),
                        "before_slots": _state(match)["slots"],
                        "after_slots": state["slots"],
                        "after_status": state["status"],
                    }
                )
        projection = {
            "matches": states,
            "changed_match_ids": changed,
            "match_impacts": impacts,
            "reset_match_ids": [],
            "reset_final_changes": [],
        }
    # Recomputing an unchanged administrative result must retain its completion time.
    unchanged = set()
    for match in matches:
        state = projection["matches"][match.pk]
        current = _state(match)
        if state["status"] == "FINAL" and state["completed_at"] is None:
            candidate = {**state, "completed_at": current["completed_at"]}
            if _json(candidate) == _json(current):
                projection["matches"][match.pk] = candidate
                unchanged.add(match.pk)
    projection["changed_match_ids"] = [
        pk for pk in projection["changed_match_ids"] if pk not in unchanged
    ]
    projection["match_impacts"] = [
        i for i in projection["match_impacts"] if i["match_id"] not in unchanged
    ]
    projection["reset_match_ids"] = [
        pk for pk in projection["reset_match_ids"] if pk not in unchanged
    ]
    # Carry causes through source routes, including routes emptied by an earlier removal.
    causes, effects = {}, {}
    for match in matches:
        state = projection["matches"][match.pk]
        owners = set()
        for slot in match.slots.all():
            if slot.resolved_entry_id in unavailable:
                owners.add(unavailable[slot.resolved_entry_id])
            if slot.source_match_id:
                source = projection["matches"][slot.source_match_id]
                routed = _routed_entry_id(
                    source["outcome"],
                    source["winner_id"],
                    [entry for _, entry in source["slots"]],
                    slot.source_outcome,
                )
                if routed in unavailable:
                    owners.add(unavailable[routed])
                owners.update(causes.get(slot.source_match_id, ()))
        if _authoritative(match):
            owners.update(
                int(pk)
                for pk in match.removal_effect["causes"]
                if any(
                    e.entrant_id == int(pk) and entry in unavailable
                    for entry, e in entries.items()
                )
            )
        if match.pk in result_updates:
            causes[match.pk] = set()
            continue
        causes[match.pk] = (
            owners
            if (match.pk in projection["changed_match_ids"] or _authoritative(match))
            else set()
        )
        if match.pk not in projection["changed_match_ids"]:
            continue
        before = baselines.get(match.pk, _state(match))
        if owners and (state["status"] == "FINAL" or state["slots"] != before["slots"]):
            effects[match.pk] = {"before": _json(before), "entrant_ids": sorted(owners)}
        else:
            effects[match.pk] = None
    projection["effects"] = effects
    projection["preserved_corrections"] = preserved
    projection["reset_match_ids"] = sorted(
        set(projection["reset_match_ids"])
        | {
            m.pk
            for m in matches
            if m.pk in projection["changed_match_ids"]
            and m.pk in baselines
            and m.status in ("LIVE", "FINAL")
            and m.outcome not in ("BYE", "EMPTY")
            and _json(projection["matches"][m.pk]) != _json(_state(m))
        }
    )
    return projection


def apply_removal_projection(draw, projection):
    apply_elimination_projection(draw, projection)
    owners = {
        str(e.pk): e.removal_change_id
        for e in draw.stage.competition.entrants.all()
        if e.status != "ACTIVE" and e.removal_change_id is not None
    }
    recorded = {}
    for pk, effect in projection["effects"].items():
        match = Match.objects.get(pk=pk)
        value = (
            {}
            if effect is None
            else {
                "active": True,
                "before": effect["before"],
                "applied": _json(_state(match)),
                "causes": {
                    str(e): owners[str(e)]
                    for e in effect["entrant_ids"]
                    if str(e) in owners
                },
            }
        )
        Match.objects.filter(pk=pk).update(removal_effect=value)
        if value:
            recorded[str(pk)] = value
    return recorded


def _update_stage_completion(draw):
    from .commands import _update_stage_completion as update

    update(draw)


def _permission(actor, payload=None):
    require_organizer(actor, "competitions.change_competition")
    if payload and (
        payload["match_impacts"]
        or payload["reset_match_ids"]
        or StageDraw.objects.filter(
            pk__in=payload["retired_draws"], published_at__isnull=False
        ).exists()
        or Round.objects.filter(
            pk__in=payload["retired_rounds"], published_at__isnull=False
        ).exists()
    ):
        require_organizer(actor, "competitions.change_match")


def _validate_transition(entrant, status):
    if not isinstance(status, str) or status not in CompetitionEntrant.Status.values:
        raise ValidationError("Choose a valid entrant status.")
    if status == entrant.status:
        raise ValidationError("The entrant already has this status.")
    if entrant.competition.ended_at is not None:
        raise ValidationError("Reopen the competition before changing entrants.")
    if status == "ACTIVE":
        if (
            entrant.registration.status != "APPROVED"
            or entrant.registration.tournament_game_id
            != entrant.competition.tournament_game_id
        ):
            raise ValidationError(
                "Restore requires the original registration to be approved for this division."
            )
        change = entrant.removal_change
        if (
            change is None
            or change.competition_id != entrant.competition_id
            or change.kind not in ("entrant_withdrawn", "entrant_disqualified")
            or not isinstance(change.private_data, dict)
            or not isinstance(change.private_data.get("boundaries"), dict)
            or not isinstance(change.private_data.get("removal_effects"), dict)
            or not isinstance(change.private_data.get("earned_resolution_ids"), list)
            or any(
                type(pk) is not int
                for pk in change.private_data["earned_resolution_ids"]
            )
            or type(change.private_data.get("entrant_id")) is not int
            or change.private_data["entrant_id"] != entrant.pk
        ):
            raise ValidationError(
                "Missing authoritative removal history. Review the entrant history before restoring."
            )


def _transition_projection(entrant, status):
    _validate_transition(entrant, status)
    competition = entrant.competition
    relabel = entrant.status != "ACTIVE" and status != "ACTIVE"
    kind = (
        "entrant_status_changed"
        if relabel
        else "entrant_restored"
        if status == "ACTIVE"
        else "entrant_withdrawn"
        if status == "WITHDRAWN"
        else "entrant_disqualified"
    )
    payload = {
        "kind": kind,
        "competition_id": competition.pk,
        "revision": competition.revision,
        "entrant_id": entrant.pk,
        "before": {"status": entrant.status},
        "after": {"status": status},
        "match_impacts": [],
        "live_forfeit_ids": [],
        "reset_match_ids": [],
        "reset_matches": [],
        "retired_draws": [],
        "retired_rounds": [],
        "blocked_handoffs": [],
        "preserved_corrections": [],
        "earned_resolution_ids": [],
        "boundaries": {},
        "invalidated_tie_ids": [],
        "authority": [],
    }
    plans = []
    if relabel:
        return payload, plans
    statuses = {entrant.pk: status}
    retired = set()
    draws = (
        StageDraw.objects.filter(stage__competition=competition)
        .exclude(state="SUPERSEDED")
        .select_related("stage")
        .order_by("stage__sequence", "pk")
    )
    for draw in draws:
        if draw.pk in retired:
            continue
        if draw.state != "PUBLISHED":
            if draw.entries.filter(entrant=entrant).exists():
                payload["retired_draws"].append(draw.pk)
            continue
        qualification_before = stage_qualification(draw)
        payload["earned_resolution_ids"].extend(
            qualification_before["earned_resolution_ids"]
        )
        payload["boundaries"][str(draw.pk)] = list(
            draw.rounds.filter(state="PUBLISHED", section="NORMAL").values_list(
                "pk", flat=True
            )
        )
        projection = project_removal_results(
            draw,
            entrant_statuses=statuses,
            restore_change_id=entrant.removal_change_id if status == "ACTIVE" else None,
        )
        payload["authority"].extend(
            [m.pk, m.removal_effect]
            for m in Match.objects.filter(round__draw=draw).order_by("pk")
            if m.removal_effect
        )
        swiss = None
        projected = projection["matches"]
        if draw.stage.format in SWISS:
            boundary = None
            if status == "ACTIVE":
                previous = entrant.removal_change.private_data.get(
                    "boundaries", {}
                ).get(str(draw.pk), [])
                later = (
                    draw.rounds.filter(section="NORMAL")
                    .exclude(state="SUPERSEDED")
                    .exclude(pk__in=previous)
                    .order_by("number")
                    .first()
                )
                boundary = later.number if later else None
            swiss = project_swiss_correction(
                draw,
                projected_matches=projected,
                entrant_statuses=statuses,
                retire_from_round=boundary,
            )
            payload["retired_rounds"].extend(swiss["retired_round_ids"])
            payload["reset_match_ids"].extend(swiss["played_match_ids"])
            projected = [
                m
                for m in projected_fixture_matches(draw, projected)
                if m.pk in swiss["current_match_ids"]
            ]
        qualification = stage_qualification(
            draw, projected_matches=projected, entrant_statuses=statuses
        )
        ties = list(
            draw.tie_resolutions.exclude(state="SUPERSEDED")
            .exclude(pk__in=qualification["resolution_states"])
            .values_list("pk", flat=True)
        )
        payload["invalidated_tie_ids"].extend(ties)
        tie_rounds = Round.objects.filter(tie_resolution_id__in=ties).exclude(
            state="SUPERSEDED"
        )
        payload["retired_rounds"].extend(tie_rounds.values_list("pk", flat=True))
        payload["reset_match_ids"].extend(
            Match.objects.filter(round__in=tie_rounds, status__in=("LIVE", "FINAL"))
            .exclude(outcome__in=("BYE", "EMPTY"))
            .values_list("pk", flat=True)
        )
        handoff = project_handoff_corrections(
            draw,
            projected_qualification=qualification,
            source_needs_replay=qualification["qualification_state"] == "PROVISIONAL",
            entrant_statuses=statuses,
        )
        retired.update(handoff["superseded_draw_ids"])
        payload["retired_draws"].extend(handoff["superseded_draw_ids"])
        payload["reset_match_ids"].extend(
            m["match_id"] for m in handoff["reset_matches"]
        )
        if qualification["qualification_state"] == "BLOCKED":
            payload["blocked_handoffs"].append(draw.stage_id)
        payload["match_impacts"].extend(projection["match_impacts"])
        payload["reset_match_ids"].extend(projection["reset_match_ids"])
        payload["preserved_corrections"].extend(projection["preserved_corrections"])
        payload["live_forfeit_ids"].extend(
            i["match_id"]
            for i in projection["match_impacts"]
            if i["before"]["status"] == "LIVE"
            and i["after"]["outcome"] in ("FORFEIT", "DOUBLE_FORFEIT")
        )
        plans.append((draw, projection, swiss, handoff))
    for key in (
        "live_forfeit_ids",
        "reset_match_ids",
        "retired_draws",
        "retired_rounds",
        "blocked_handoffs",
        "preserved_corrections",
        "earned_resolution_ids",
        "invalidated_tie_ids",
    ):
        payload[key] = sorted(set(payload[key]))
    payload["reset_matches"] = [
        _match_snapshot(match)
        for match in Match.objects.filter(pk__in=payload["reset_match_ids"])
        .select_related("winner__entrant")
        .prefetch_related("slots__resolved_entry__entrant")
        .order_by("pk")
    ]
    return _json(payload), plans


def _response(payload, token=None):
    return {
        **payload,
        "token": token or signing.dumps(payload, salt=LIFECYCLE_SALT, compress=True),
    }


def preview_entrant_transition(
    *, actor, entrant_id: int, expected_revision: int, status: str
) -> dict:
    _permission(actor)
    if type(entrant_id) is not int or type(expected_revision) is not int:
        raise ValidationError("Entrant and revision must be integers.")
    try:
        entrant = CompetitionEntrant.objects.select_related(
            "competition", "registration", "removal_change"
        ).get(pk=entrant_id)
    except CompetitionEntrant.DoesNotExist as error:
        raise ValidationError("Unknown competition entrant.") from error
    _check_revision(entrant.competition, expected_revision)
    payload, _ = _transition_projection(entrant, status)
    _permission(actor, payload)
    return _response(payload)


def _load_token(token):
    try:
        if not isinstance(token, str):
            raise ValueError
        payload = signing.loads(token, salt=LIFECYCLE_SALT, max_age=3600)
        if (
            not isinstance(payload, dict)
            or payload.get("kind")
            not in (
                "entrant_withdrawn",
                "entrant_disqualified",
                "entrant_restored",
                "entrant_status_changed",
            )
            or any(
                type(payload.get(k)) is not int
                for k in ("entrant_id", "competition_id", "revision")
            )
            or not isinstance(payload.get("after"), dict)
            or not isinstance(payload["after"].get("status"), str)
        ):
            raise ValueError
        return payload
    except (signing.BadSignature, ValueError, TypeError) as error:
        raise ValidationError("The lifecycle preview is invalid or expired.") from error


def review_lifecycle_preview(*, actor, token: str) -> dict:
    submitted = _load_token(token)
    response = preview_entrant_transition(
        actor=actor,
        entrant_id=submitted["entrant_id"],
        expected_revision=submitted["revision"],
        status=submitted["after"]["status"],
    )
    if {k: v for k, v in response.items() if k != "token"} != submitted:
        raise ValidationError("The lifecycle impact changed. Preview it again.")
    return {**response, "token": token}


def apply_entrant_transition(
    *,
    actor,
    token: str,
    internal_reason: str,
    confirm_live_forfeits: bool = False,
    confirm_resets: bool = False,
) -> CompetitionEntrant:
    _permission(actor)
    if not isinstance(internal_reason, str) or not internal_reason.strip():
        raise ValidationError("A private reason is required.")
    if type(confirm_live_forfeits) is not bool or type(confirm_resets) is not bool:
        raise ValidationError("Impact confirmations must be booleans.")
    submitted = _load_token(token)
    with transaction.atomic():
        try:
            competition = _lock_competition(submitted["competition_id"])
        except Competition.DoesNotExist as error:
            raise ValidationError("Unknown competition.") from error
        _check_revision(competition, submitted["revision"])
        try:
            entrant = CompetitionEntrant.objects.select_for_update().get(
                pk=submitted["entrant_id"], competition=competition
            )
        except CompetitionEntrant.DoesNotExist as error:
            raise ValidationError(
                "The entrant does not belong to this competition."
            ) from error
        entrant.competition = competition
        list(
            Match.objects.select_for_update()
            .filter(round__draw__stage__competition=competition)
            .order_by("pk")
        )
        list(
            MatchSlot.objects.select_for_update()
            .filter(match__round__draw__stage__competition=competition)
            .order_by("pk")
        )
        payload, plans = _transition_projection(entrant, submitted["after"]["status"])
        if payload != submitted:
            raise ValidationError("The lifecycle impact changed. Preview it again.")
        _permission(actor, payload)
        if payload["live_forfeit_ids"] and not confirm_live_forfeits:
            raise ValidationError("Confirm the live-match forfeits.")
        if payload["reset_match_ids"] and not confirm_resets:
            raise ValidationError("Confirm the affected result resets.")
        public = {
            "kind": payload["kind"],
            "entrant_id": entrant.pk,
            "display_name": entrant.display_name,
            "before": payload["before"],
            "after": payload["after"],
            "match_impacts": payload["match_impacts"],
        }
        public["reset_match_ids"] = list(
            Match.objects.filter(
                pk__in=payload["reset_match_ids"],
                round__published_at__isnull=False,
                round__draw__published_at__isnull=False,
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        public["reset_matches"] = [
            snapshot
            for snapshot in payload["reset_matches"]
            if snapshot["match_id"] in public["reset_match_ids"]
        ]
        public["retired_draws"] = list(
            StageDraw.objects.filter(
                pk__in=payload["retired_draws"], published_at__isnull=False
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        public["retired_rounds"] = list(
            Round.objects.filter(
                pk__in=payload["retired_rounds"],
                published_at__isnull=False,
                draw__published_at__isnull=False,
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if not entrant.stage_entries.filter(draw__published_at__isnull=False).exists():
            public = {}
        change = _record_change(
            competition,
            actor=actor,
            kind=payload["kind"],
            internal_reason=internal_reason,
            private_data=payload,
            public_data=public,
        )
        entrant.status = payload["after"]["status"]
        if payload["kind"] in ("entrant_withdrawn", "entrant_disqualified"):
            entrant.removal_change = change
        elif entrant.status == "ACTIVE":
            entrant.removal_change = None
        entrant.save(update_fields=["status", "removal_change"])
        effects = {}
        for draw, projection, swiss, handoff in plans:
            effects.update(apply_removal_projection(draw, projection))
            if swiss:
                apply_swiss_correction(draw, swiss)
            apply_handoff_impact(handoff)
        _supersede_ties(
            TieResolution.objects.filter(pk__in=payload["invalidated_tie_ids"])
        )
        _supersede_draws(StageDraw.objects.filter(pk__in=payload["retired_draws"]))
        for draw, _, _, _ in plans:
            if draw.pk not in payload["retired_draws"]:
                _update_stage_completion(draw)
        change.private_data = {**change.private_data, "removal_effects": effects}
        change.save(update_fields=["private_data"])
        return entrant
