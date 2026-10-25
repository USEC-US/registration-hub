"""Presentation data for the organizer workspace; mutations stay in commands."""

from urllib.parse import urlencode

from django.urls import reverse
from django.db.models import Q

from .models import Match, Round, Stage, StageDraw, StageEntry


def series_label(mode, length):
    return f"Fixed {length} games" if mode == "FIXED_GAMES" else f"Best of {length}"


def workspace_url(competition_id, tab=None, *, stage_id=None):
    url = reverse("admin:competitions_competition_change", args=[competition_id])
    params = {}
    if tab:
        params["tab"] = tab
    if stage_id is not None:
        params["stage"] = stage_id
    return f"{url}?{urlencode(params)}" if params else url


def slot_label(slot):
    entry = slot.resolved_entry or slot.entry
    if entry:
        return entry.entrant.display_name
    if slot.is_resolved or slot.is_empty:
        return "Bye"
    if slot.source_match_id:
        return f"{slot.get_source_outcome_display()} of {slot.source_match.code}"
    return "Opponent to be decided"


def grand_final_policy_label(stage):
    if not stage or stage.format != Stage.Format.DOUBLE_ELIMINATION:
        return ""
    if stage.grand_final_policy == Stage.GrandFinalPolicy.RESET:
        return "Reset if necessary"
    return "No reset"


def round_label(round_, *, last_round_number):
    if round_.draw.stage.format in (
        Stage.Format.ROUND_ROBIN,
        Stage.Format.SWISS_FIXED,
        Stage.Format.SWISS_THRESHOLD,
    ):
        return f"{'Extra contest round' if round_.section == 'TIEBREAK' else 'Round'} {round_.number}"
    if round_.section == Round.Section.FINALS:
        return "Grand final" if round_.number == 1 else "Reset final"
    if round_.section in (Round.Section.UPPER, Round.Section.LOWER):
        bracket = round_.get_section_display()
        return (
            f"{bracket} bracket final"
            if round_.number == last_round_number
            else f"{bracket} bracket round {round_.number}"
        )
    remaining = last_round_number - round_.number + 1
    return {1: "Final", 2: "Semifinals", 3: "Quarterfinals"}.get(
        remaining, f"Round {round_.number}"
    )


def match_card(match, user):
    slots = list(match.slots.all())
    published = (
        match.round.draw.state == StageDraw.State.PUBLISHED
        and match.round.state == Round.State.PUBLISHED
    )
    ready = len(slots) == 2 and all(
        slot.is_resolved and slot.resolved_entry_id for slot in slots
    )
    historical = (
        match.round.draw.stage.competition.ended_at is not None
        or match.round.state == Round.State.SUPERSEDED
        or match.round.draw.state == StageDraw.State.SUPERSEDED
        or (
            match.round.tie_resolution_id
            and match.round.tie_resolution.state == "SUPERSEDED"
        )
    )
    can_operate = (
        user.has_perm("competitions.change_match") and published and not historical
    )
    automatic = match.outcome in (Match.Outcome.BYE, Match.Outcome.EMPTY)
    inactive_final = match.status in (
        Match.Status.CONDITIONAL,
        Match.Status.NOT_REQUIRED,
    )
    result_url = None
    result_label = "Enter result"
    if (
        can_operate
        and ready
        and match.status in (Match.Status.PENDING, Match.Status.LIVE)
    ):
        result_url = reverse(
            "admin:competitions_match_finalize_detail", args=[match.pk]
        )
    elif can_operate and match.status == Match.Status.FINAL and not automatic:
        if user.has_perm("competitions.change_competition"):
            result_url = reverse(
                "admin:competitions_match_correct_detail", args=[match.pk]
            )
            result_label = "Correct result"
    status = match.get_status_display()
    if match.status == Match.Status.PENDING:
        status = "Ready to play" if ready else "Waiting for opponents"
    elif automatic:
        status = "Bye" if match.outcome == Match.Outcome.BYE else "No contest"
    elif match.status == Match.Status.FINAL:
        status = "Completed"
    elif match.status == Match.Status.CONDITIONAL:
        status = "Reserved final"
    return {
        "id": match.pk,
        "code": match.code,
        "title": " vs ".join(slot_label(slot) for slot in slots),
        "slots": [
            {
                "label": slot_label(slot),
                "position": slot.position,
                "source_match_id": slot.source_match_id,
                "source_outcome": slot.source_outcome,
                "seed": (slot.resolved_entry or slot.entry).seed
                if slot.resolved_entry_id or slot.entry_id
                else None,
                "score": ("W" if slot.resolved_entry_id == match.winner_id else "FF")
                if match.outcome == Match.Outcome.FORFEIT
                else (
                    match.side_one_score if slot.position == 1 else match.side_two_score
                ),
                "is_winner": bool(
                    match.winner_id and slot.resolved_entry_id == match.winner_id
                ),
            }
            for slot in slots
        ],
        "status": status,
        "outcome": "Draw"
        if match.status == "FINAL"
        and match.outcome == "PLAYED"
        and not match.winner_id
        and match.effective_series_mode == "FIXED_GAMES"
        else match.get_outcome_display(),
        "series_length": match.effective_series_length,
        "series_label": series_label(
            match.effective_series_mode, match.effective_series_length
        ),
        "scheduled_at": match.scheduled_at,
        "detail_url": reverse("admin:competitions_match_change", args=[match.pk]),
        "result_url": result_url,
        "result_label": result_label,
        "schedule_url": reverse(
            "admin:competitions_match_schedule_detail", args=[match.pk]
        )
        if can_operate
        and match.status
        in (Match.Status.PENDING, Match.Status.CONDITIONAL, Match.Status.NOT_REQUIRED)
        else None,
        "awaiting": not ready and not automatic and not inactive_final,
        "inactive_final": inactive_final,
        "inactive_final_message": (
            "This reserved final activates if the lower-bracket winner wins the grand final."
            if match.status == Match.Status.CONDITIONAL
            else "This reserved final is not required for the current grand final result."
            if match.status == Match.Status.NOT_REQUIRED
            else ""
        ),
        "historical": bool(historical),
        "closed": bool(
            match.round.draw.stage.competition.ended_at
            and match.round.draw.stage.competition.ended_stage_id
            == match.round.draw.stage_id
        ),
        "private": match.round.state == Round.State.DRAFT
        or match.round.draw.state == StageDraw.State.DRAFT,
        "can_operate": can_operate,
    }


def result_summary(snapshot):
    if not snapshot:
        return ""
    one = snapshot.get("side_one") or "Opponent to be decided"
    two = snapshot.get("side_two") or "Opponent to be decided"
    first_score = snapshot.get("side_one_score")
    second_score = snapshot.get("side_two_score")
    scores = f"{first_score if first_score is not None else '—'}–{second_score if second_score is not None else '—'}"
    outcome = dict(Match.Outcome.choices).get(snapshot.get("outcome"), "")
    winner = snapshot.get("winner")
    pairing = (
        f"{one} {scores} {two}"
        if snapshot.get("side_one") or snapshot.get("side_two")
        else f"{snapshot.get('match_code', 'Match')} · {scores}"
    )
    return (
        pairing
        + (f" · {outcome}" if outcome else "")
        + (f" · Winner: {winner}" if winner else "")
    )


def correction_display(impact):
    group = impact.get("group_impact")
    group_display = None
    if group:
        ids = [
            row["entry_id"]
            for key in ("before", "after")
            for row in group[key]["standings"]
        ]
        names = dict(
            StageEntry.objects.filter(pk__in=ids).values_list(
                "pk", "entrant__display_name"
            )
        )
        group_display = {
            **group,
            "after_rows": [
                {**row, "name": names[row["entry_id"]]}
                for row in group["after"]["standings"]
            ],
            "before_qualifiers": [names[pk] for pk in group["before"]["qualifiers"]],
            "after_qualifiers": [names[pk] for pk in group["after"]["qualifiers"]],
            "historical_matches": [
                {
                    "code": item["match_code"],
                    "status": dict(Match.Status.choices)[item["status"]],
                    "label": result_summary(item),
                    "url": reverse(
                        "admin:competitions_match_change", args=[item["match_id"]]
                    ),
                }
                for item in group["historical_matches"]
            ],
        }
    swiss = impact.get("swiss_impact")
    swiss_display = None
    if swiss:
        rounds = (
            Round.objects.filter(pk__in=swiss["retired_round_ids"])
            .select_related("draw__stage")
            .order_by("number", "version")
        )
        matches = (
            Match.objects.filter(pk__in=swiss["played_match_ids"])
            .select_related("round__draw__stage", "winner__entrant")
            .prefetch_related("slots__resolved_entry__entrant")
        )
        swiss_display = {
            "rounds": [
                {
                    "id": r.pk,
                    "label": f"{r.draw.stage.name} · Round {r.number}, version {r.version}",
                    "state": r.get_state_display(),
                }
                for r in rounds
            ],
            "retired_match_count": len(swiss["retired_match_ids"]),
            "played_matches": [
                {
                    "code": m.code,
                    "title": " vs ".join(slot_label(slot) for slot in m.slots.all()),
                    "scores": f"{m.side_one_score if m.side_one_score is not None else '—'}–{m.side_two_score if m.side_two_score is not None else '—'}",
                    "url": reverse("admin:competitions_match_change", args=[m.pk]),
                }
                for m in matches
            ],
        }
    return {
        "swiss": swiss_display,
        "group": group_display,
        "handoff": impact.get("handoff_impact"),
        "retired_results": [
            result_summary(m)
            for m in impact.get("handoff_impact", {}).get("reset_matches", [])
        ],
        "before": result_summary(impact.get("before")),
        "after": result_summary(impact.get("after")),
        "matches": [
            {
                "code": item["match_code"],
                "label": result_summary(item),
                "url": reverse(
                    "admin:competitions_match_change", args=[item["match_id"]]
                ),
            }
            for item in impact.get("affected_matches", [])
            if item.get("status") in (Match.Status.LIVE, Match.Status.FINAL)
        ],
        "activation_changes": reset_final_changes_display(
            impact.get("reset_final_changes", [])
        ),
    }


def reset_final_changes_display(changes):
    labels = {
        "ACTIVE": "Active",
        "CONDITIONAL": "Reserved",
        "NOT_REQUIRED": "Not required",
    }
    return [
        {
            "code": item["match_code"],
            "before": labels[item["before"]],
            "after": labels[item["after"]],
            "url": reverse("admin:competitions_match_change", args=[item["match_id"]]),
        }
        for item in changes
    ]


def swiss_workspace(draw):
    """Read saved fixtures and current standings; never validate by solving on GET."""
    from .swiss_commands import swiss_standings, _rank, _swiss_results

    rows = swiss_standings(draw)
    names = dict(draw.entries.values_list("pk", "entrant__display_name"))
    current = (
        draw.rounds.filter(section="NORMAL")
        .exclude(state="SUPERSEDED")
        .order_by("-number")
        .first()
    )
    published = draw.rounds.filter(section="NORMAL", state="PUBLISHED")
    change = (
        draw.stage.competition.changes.filter(
            private_data__swiss_round__round_id=current.pk
        ).first()
        if current
        else None
    )
    audit = change.private_data if change else {}
    bye_id = audit.get("swiss_round", {}).get("bye_entry_id")
    previous_rows = (
        _rank(draw, _swiss_results(draw, before_number=current.number))
        if current
        else []
    )
    return {
        "round": current,
        "limit": draw.swiss_round_limit,
        "rows": [{"row": row, "name": names[row.entry_id]} for row in rows],
        "bye": names.get(bye_id),
        "repeated_bye": any(
            row.entry_id == bye_id and row.bye_count for row in previous_rows
        ),
        "repeat_pairs": [
            [names[a], names[b]] for a, b in audit.get("repeat_pairs", [])
        ],
        "cross_group_pairs": [
            [names[a], names[b]] for a, b in audit.get("cross_group_pairs", [])
        ],
        "can_generate": bool(
            draw.state == "PUBLISHED"
            and current
            and current.state == "PUBLISHED"
            and not current.matches.exclude(status="FINAL").exists()
            and draw.stage.status != "COMPLETE"
            and published.count() < draw.swiss_round_limit
        ),
    }


def lifecycle_display(impact, competition, user):
    """Resolve signed IDs within this competition into readable impact lists."""
    affected = [i["match_id"] for i in impact.get("match_impacts", [])]
    ids = set(
        affected
        + impact.get("reset_match_ids", [])
        + impact.get("preserved_corrections", [])
    )
    matches = (
        Match.objects.filter(round__draw__stage__competition=competition)
        .filter(
            Q(pk__in=ids)
            | Q(round__draw_id__in=impact.get("retired_draws", []))
            | Q(round_id__in=impact.get("retired_rounds", []))
        )
        .select_related("round__draw__stage")
        .prefetch_related(
            "slots__entry__entrant",
            "slots__resolved_entry__entrant",
            "slots__source_match",
        )
    )
    by_id = {m.pk: m for m in matches}

    def describe(ids):
        rows = []
        for pk in sorted(set(ids)):
            m = by_id.get(pk)
            if m:
                card = match_card(m, user)
                rows.append(
                    f"{m.round.draw.stage.name} · {m.code} — {card['title']} · {m.get_status_display()} · {m.side_one_score if m.side_one_score is not None else '—'}–{m.side_two_score if m.side_two_score is not None else '—'} · {m.get_outcome_display()}"
                )
        return rows

    retired_matches = [
        m.pk
        for m in by_id.values()
        if m.round.draw_id in impact.get("retired_draws", [])
        or m.round_id in impact.get("retired_rounds", [])
    ]

    def outcome(snapshot):
        if "status" in snapshot:
            return snapshot["status"].replace("_", " ").capitalize()
        stage = competition.stages.filter(pk=snapshot.get("stage_id")).first()
        champion = competition.entrants.filter(pk=snapshot.get("champion_id")).first()
        ended = snapshot.get("ended", bool(snapshot.get("ended_at")))
        return f"{'Ended' if ended else 'Open'}{f' · {stage.name}' if stage else ''} · {'Champion: ' + champion.display_name if champion else 'Without a champion'}"

    effects = {i["match_id"]: i["after"] for i in impact.get("match_impacts", [])}
    return {
        "before": outcome(impact["before"]),
        "after": outcome(impact["after"]),
        "effects": [
            f"{by_id[pk].code}: {'Closed / frozen' if after.get('frozen') else 'Reopened' if 'frozen' in after else result_summary(after)}"
            for pk, after in effects.items()
            if pk in by_id
        ],
        "affected": describe(affected),
        "resets": describe(impact.get("reset_match_ids", [])),
        "preserved": describe(impact.get("preserved_corrections", [])),
        "historical": describe(retired_matches),
        "stages": list(
            competition.stages.filter(draws__pk__in=impact.get("retired_draws", []))
            .values_list("name", flat=True)
            .distinct()
        ),
        "blocked": list(
            competition.stages.filter(
                pk__in=impact.get("blocked_handoffs", [])
            ).values_list("name", flat=True)
        ),
    }
