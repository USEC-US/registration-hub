"""Signed entrant transitions; projections are read-only and applies own the transaction."""

import json
from copy import copy

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from config.organizers import require_organizer
from .command_support import (
    require_competition_open,
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
    require_competition_open(entrant.competition)
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
        if not isinstance(payload, dict) or any(
            type(payload.get(k)) is not int for k in ("competition_id", "revision")
        ):
            raise ValueError
        kind = payload.get("kind")
        if kind in (
            "entrant_withdrawn",
            "entrant_disqualified",
            "entrant_restored",
            "entrant_status_changed",
        ):
            if (
                type(payload.get("entrant_id")) is not int
                or not isinstance(payload.get("after"), dict)
                or not isinstance(payload["after"].get("status"), str)
            ):
                raise ValueError
        elif kind in ("competition_ended", "competition_reopened"):
            if type(payload.get("stage_id")) is not int:
                raise ValueError
            if (
                kind == "competition_ended"
                and type(payload.get("award_sole_survivor")) is not bool
            ):
                raise ValueError
        else:
            raise ValueError
        return payload
    except (signing.BadSignature, ValueError, TypeError) as error:
        raise ValidationError("The lifecycle preview is invalid or expired.") from error


def review_lifecycle_preview(*, actor, token: str) -> dict:
    submitted = _load_token(token)
    if submitted["kind"] == "competition_ended":
        response = preview_competition_end(
            actor=actor,
            stage_id=submitted["stage_id"],
            expected_revision=submitted["revision"],
            award_sole_survivor=submitted["award_sole_survivor"],
        )
    elif submitted["kind"] == "competition_reopened":
        response = preview_competition_reopen(
            actor=actor,
            competition_id=submitted["competition_id"],
            expected_revision=submitted["revision"],
        )
    else:
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
    if not submitted["kind"].startswith("entrant_"):
        raise ValidationError("Choose an entrant transition preview.")
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


def _ending_candidates(draw):
    """Prove a blocked continuation without inventing results or replacing qualifiers."""
    from .qualification import entry_eligibility
    from .stage_commands import validate_stage_field
    from .swiss_commands import swiss_standings

    stage = draw.stage
    qualification = stage_qualification(draw)
    entries = list(draw.entries.select_related("entrant__registration"))
    eligibility = entry_eligibility(entries)
    eligible = {
        e.pk
        for e in entries
        if eligibility[e.pk]
        and e.entrant.competition_id == stage.competition_id
        and e.entrant.registration.tournament_game_id
        == stage.competition.tournament_game_id
    }
    later = list(
        stage.competition.stages.filter(sequence__gt=stage.sequence).prefetch_related(
            "group_plans"
        )
    )
    quota = (
        sum(p.qualifying_places for p in stage.group_plans.all())
        if stage.format == Stage.Format.ROUND_ROBIN
        else stage.advancement_count
    )
    # Validate rules on their saved field, never silently repair malformed configuration.
    validate_stage_field(stage, len(entries))
    state = qualification["qualification_state"]
    reason = None
    candidates = set(qualification["qualifier_entry_ids"]) & eligible
    determinable = state != "PROVISIONAL" and not qualification["cutoffs"]
    if state == "PROVISIONAL":
        possible = eligible
        if stage.format == Stage.Format.SWISS_THRESHOLD:
            rows = swiss_standings(draw)
            possible = {
                row.entry_id for row in rows if row.status != "ELIMINATED"
            } & eligible
            earned_count = sum(
                row.status == "QUALIFIED" and row.entry_id in eligible for row in rows
            )
            if later:
                # Bounds prove impossibility without predicting future match results.
                for incoming in range(earned_count, len(possible) + 1):
                    try:
                        for destination in later:
                            incoming, _ = validate_stage_field(destination, incoming)
                    except ValidationError:
                        continue
                    break
                else:
                    reason = "No remaining possible qualifying field fits the locked continuation."
        if not possible:
            reason = "There are no eligible participants remaining."
        elif later and len(possible) < (quota if quota is not None else 2):
            reason = "The remaining eligible field cannot fill the locked continuation."
        if stage.format == Stage.Format.ROUND_ROBIN and any(
            len(eligible & {e.pk for e in entries if e.group_id == group.pk})
            < group.qualifying_places
            for group in draw.groups.all()
        ):
            reason = "An eligible group field cannot fill its locked qualifying quota."
        # An incomplete ranking cannot establish an earned qualifier.
        candidates = possible if stage.format in SWISS else set()
        determinable = stage.format in SWISS and len(possible) == 1
    elif qualification["block_reason"]:
        reason = qualification["block_reason"]
    if state != "PROVISIONAL" and later and not qualification["cutoffs"]:
        incoming = len(candidates)
        if quota is not None and incoming != quota:
            reason = (
                reason or "The earned eligible qualifiers cannot fill the locked quota."
            )
        else:
            for destination in later:
                try:
                    incoming, _ = validate_stage_field(destination, incoming)
                except ValidationError as error:
                    reason = "; ".join(error.messages)
                    break
    if not later and stage.format in ELIMINATION and state != "PROVISIONAL":
        stage.refresh_from_db()
        candidates = {
            e.pk for e in entries if e.entrant_id == stage.champion_id
        } & eligible
        if not candidates:
            reason = (
                reason
                or "No eligible champion can be determined from the source results."
            )
    if reason is None:
        raise ValidationError(
            "Finish viable contests and resolve cutoffs; the locked continuation is still possible."
        )
    champion = (
        next((e.entrant_id for e in entries if e.pk in candidates), None)
        if determinable and len(candidates) == 1
        else None
    )
    return qualification, reason, champion


def _competition_outcome(competition):
    return {
        "ended_at": competition.ended_at.isoformat() if competition.ended_at else None,
        "stage_id": competition.ended_stage_id,
        "champion_id": competition.ended_champion_id,
    }


def _ending_payload(competition, stage, *, award_sole_survivor=False, reopen=False):
    if reopen:
        if competition.ended_at is None or competition.ended_stage_id != stage.pk:
            raise ValidationError(
                "Only an exceptionally ended competition can be reopened."
            )
        reason = None
        champion = None
        qualification = None
    else:
        require_competition_open(competition)
        draw = stage.draws.filter(state="PUBLISHED").first()
        if draw is None:
            raise ValidationError("Choose a published source stage.")
        qualification, reason, champion = _ending_candidates(draw)
        if award_sole_survivor and champion is None:
            raise ValidationError(
                "Only a determinable sole eligible survivor can be awarded; choose Without a champion."
            )
    draws = (
        list(
            StageDraw.objects.filter(
                stage__competition=competition, stage__sequence__gt=stage.sequence
            )
            .exclude(state="SUPERSEDED")
            .order_by("pk")
        )
        if not reopen
        else []
    )
    rounds = list(
        Round.objects.filter(draw__in=draws).exclude(state="SUPERSEDED").order_by("pk")
    )
    source = stage.draws.filter(state="PUBLISHED").first()
    frozen = list(
        Match.objects.filter(round__draw=source, round__state="PUBLISHED")
        .exclude(status__in=("FINAL", "NOT_REQUIRED"))
        .select_related("winner__entrant")
        .prefetch_related("slots__resolved_entry__entrant")
        .order_by("pk")
    )
    reset = list(
        Match.objects.filter(round__draw__in=draws, status__in=("LIVE", "FINAL"))
        .exclude(outcome__in=("BYE", "EMPTY"))
        .select_related("winner__entrant")
        .prefetch_related("slots__resolved_entry__entrant")
        .order_by("pk")
    )
    return {
        "kind": "competition_reopened" if reopen else "competition_ended",
        "competition_id": competition.pk,
        "revision": competition.revision,
        "stage_id": stage.pk,
        "award_sole_survivor": award_sole_survivor,
        "before": _competition_outcome(competition),
        "after": {
            "ended": not reopen,
            "stage_id": None if reopen else stage.pk,
            "champion_id": champion if award_sole_survivor else None,
        },
        "match_impacts": [
            {
                "match_id": m.pk,
                "before": _match_snapshot(m),
                "after": {"frozen": not reopen},
            }
            for m in frozen
        ],
        "live_forfeit_ids": [],
        "frozen_match_ids": [m.pk for m in frozen],
        "reset_match_ids": [m.pk for m in reset],
        "reset_matches": [_match_snapshot(m) for m in reset],
        "retired_draws": [d.pk for d in draws],
        "retired_rounds": [r.pk for r in rounds],
        "blocked_handoffs": []
        if reopen
        else sorted(
            s.pk for s in competition.stages.filter(sequence__gt=stage.sequence)
        ),
        "preserved_corrections": [],
        "block_reason": reason,
        "source_fingerprint": qualification["fingerprint"] if qualification else None,
        "requires_confirmation": reopen
        or any(m.status == "LIVE" for m in frozen)
        or any(d.published_at is not None for d in draws),
    }


def _ending_permission(actor, payload):
    _permission(actor)
    if payload["requires_confirmation"]:
        require_organizer(actor, "competitions.change_match")


def preview_competition_end(
    *, actor, stage_id: int, expected_revision: int, award_sole_survivor: bool = False
) -> dict:
    _permission(actor)
    if (
        type(stage_id) is not int
        or type(expected_revision) is not int
        or type(award_sole_survivor) is not bool
    ):
        raise ValidationError(
            "Use an integer source/revision and an explicit boolean award choice."
        )
    try:
        stage = Stage.objects.select_related("competition").get(pk=stage_id)
    except Stage.DoesNotExist as error:
        raise ValidationError("Unknown source stage.") from error
    _check_revision(stage.competition, expected_revision)
    payload = _ending_payload(
        stage.competition, stage, award_sole_survivor=award_sole_survivor
    )
    _ending_permission(actor, payload)
    return _response(payload)


def preview_competition_reopen(
    *, actor, competition_id: int, expected_revision: int
) -> dict:
    _permission(actor)
    require_organizer(actor, "competitions.change_match")
    if type(competition_id) is not int or type(expected_revision) is not int:
        raise ValidationError("Competition and revision must be integers.")
    try:
        competition = Competition.objects.select_related("ended_stage").get(
            pk=competition_id
        )
    except Competition.DoesNotExist as error:
        raise ValidationError("Unknown competition.") from error
    _check_revision(competition, expected_revision)
    if (
        competition.ended_stage is None
        or competition.ended_stage.competition_id != competition.pk
    ):
        raise ValidationError(
            "Choose an exceptionally ended competition with a valid source."
        )
    payload = _ending_payload(competition, competition.ended_stage, reopen=True)
    return _response(payload)


def _apply_competition_outcome(
    *, actor, token, internal_reason, confirm_resets, reopen
):
    _permission(actor)
    if not isinstance(internal_reason, str) or not internal_reason.strip():
        raise ValidationError("A private reason is required.")
    if type(confirm_resets) is not bool:
        raise ValidationError("Impact confirmation must be a boolean.")
    submitted = _load_token(token)
    if submitted["kind"] != ("competition_reopened" if reopen else "competition_ended"):
        raise ValidationError("Choose the matching competition lifecycle preview.")
    with transaction.atomic():
        try:
            competition = _lock_competition(
                submitted["competition_id"], require_open=not reopen
            )
            _check_revision(competition, submitted["revision"])
            stage = Stage.objects.get(pk=submitted["stage_id"], competition=competition)
        except (Competition.DoesNotExist, Stage.DoesNotExist) as error:
            raise ValidationError(
                "The source does not belong to this competition."
            ) from error
        stage.competition = competition
        for model, scope in (
            (Stage, {"competition": competition}),
            (StageDraw, {"stage__competition": competition}),
            (Round, {"draw__stage__competition": competition}),
            (TieResolution, {"draw__stage__competition": competition}),
            (Match, {"round__draw__stage__competition": competition}),
        ):
            list(model.objects.select_for_update().filter(**scope).order_by("pk"))
        payload = _ending_payload(
            competition,
            stage,
            award_sole_survivor=submitted.get("award_sole_survivor", False),
            reopen=reopen,
        )
        if payload != submitted:
            raise ValidationError("The lifecycle impact changed. Preview it again.")
        _ending_permission(actor, payload)
        if payload["requires_confirmation"] and not confirm_resets:
            raise ValidationError(
                "Confirm the affected frozen/retired results or reopening."
            )
        public_draws = list(
            StageDraw.objects.filter(
                pk__in=payload["retired_draws"], published_at__isnull=False
            ).values_list("pk", flat=True)
        )
        public_rounds = list(
            Round.objects.filter(
                pk__in=payload["retired_rounds"],
                published_at__isnull=False,
                draw__published_at__isnull=False,
            ).values_list("pk", flat=True)
        )
        public_reset_ids = list(
            Match.objects.filter(
                pk__in=payload["reset_match_ids"],
                round__published_at__isnull=False,
                round__draw__published_at__isnull=False,
            ).values_list("pk", flat=True)
        )
        if not reopen:
            _supersede_ties(
                TieResolution.objects.filter(
                    draw_id__in=payload["retired_draws"]
                ).exclude(state="SUPERSEDED")
            )
            _supersede_draws(StageDraw.objects.filter(pk__in=payload["retired_draws"]))
            for suffix in competition.stages.filter(sequence__gt=stage.sequence):
                suffix.status = "AWAITING" if suffix.published_at else "DRAFT"
                suffix.champion = None
                suffix.completed_at = None
                suffix.completed_without_champion = False
                suffix.save(
                    update_fields=[
                        "status",
                        "champion",
                        "completed_at",
                        "completed_without_champion",
                    ]
                )
        competition.ended_at = None if reopen else timezone.now()
        competition.ended_stage = None if reopen else stage
        competition.ended_champion_id = payload["after"]["champion_id"]
        competition.save(update_fields=["ended_at", "ended_stage", "ended_champion"])
        _record_change(
            competition,
            actor=actor,
            kind=payload["kind"],
            internal_reason=internal_reason,
            private_data=payload,
            public_data={
                "kind": payload["kind"],
                "stage_id": stage.pk,
                "before": payload["before"],
                "after": _competition_outcome(competition),
                "match_impacts": payload["match_impacts"],
                "retired_draws": sorted(public_draws),
                "retired_rounds": sorted(public_rounds),
                "reset_match_ids": sorted(public_reset_ids),
                "reset_matches": [
                    m
                    for m in payload["reset_matches"]
                    if m["match_id"] in public_reset_ids
                ],
            },
        )
        return competition


def apply_competition_end(
    *, actor, token: str, internal_reason: str, confirm_resets: bool = False
) -> Competition:
    return _apply_competition_outcome(
        actor=actor,
        token=token,
        internal_reason=internal_reason,
        confirm_resets=confirm_resets,
        reopen=False,
    )


def apply_competition_reopen(
    *, actor, token: str, internal_reason: str, confirm_resets: bool = False
) -> Competition:
    return _apply_competition_outcome(
        actor=actor,
        token=token,
        internal_reason=internal_reason,
        confirm_resets=confirm_resets,
        reopen=True,
    )
