"""Presentation data for the organizer workspace; mutations stay in commands."""

from django.urls import reverse

from .models import Match, StageDraw


def workspace_url(competition_id, tab=None):
    url = reverse("admin:competitions_competition_change", args=[competition_id])
    return f"{url}?tab={tab}" if tab else url


def slot_label(slot):
    entry = slot.resolved_entry or slot.entry
    if entry:
        return entry.entrant.display_name
    if slot.is_resolved or slot.is_empty:
        return "Bye"
    if slot.source_match_id:
        return f"Winner of {slot.source_match.code}"
    return "Opponent to be decided"


def match_card(match, user):
    slots = list(match.slots.all())
    published = match.round.draw.state == StageDraw.State.PUBLISHED
    ready = len(slots) == 2 and all(
        slot.is_resolved and slot.resolved_entry_id for slot in slots
    )
    can_operate = user.has_perm("competitions.change_match") and published
    automatic = match.outcome in (Match.Outcome.BYE, Match.Outcome.EMPTY)
    result_url = None
    result_label = "Enter result"
    if can_operate and ready and match.status != Match.Status.FINAL:
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
    return {
        "id": match.pk,
        "code": match.code,
        "title": " vs ".join(slot_label(slot) for slot in slots),
        "slots": [
            {
                "label": slot_label(slot),
                "seed": (slot.resolved_entry or slot.entry).seed
                if slot.resolved_entry_id or slot.entry_id
                else None,
                "score": match.side_one_score
                if slot.position == 1
                else match.side_two_score,
                "is_winner": bool(
                    match.winner_id and slot.resolved_entry_id == match.winner_id
                ),
            }
            for slot in slots
        ],
        "status": status,
        "outcome": match.get_outcome_display(),
        "series_length": match.effective_series_length,
        "scheduled_at": match.scheduled_at,
        "detail_url": reverse("admin:competitions_match_change", args=[match.pk]),
        "result_url": result_url,
        "result_label": result_label,
        "schedule_url": reverse(
            "admin:competitions_match_schedule_detail", args=[match.pk]
        )
        if can_operate and match.status == Match.Status.PENDING
        else None,
        "awaiting": not ready and not automatic,
        "historical": match.round.draw.state == StageDraw.State.SUPERSEDED,
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
    return {
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
        ],
    }
