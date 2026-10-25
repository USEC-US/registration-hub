from urllib.parse import urlencode

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core import signing
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import TabularInline
from unfold.decorators import action

from config.organizers import is_organizer_staff, require_organizer
from tournaments.admin import OrganizerStaffAdmin
from tournaments.models import TournamentGame

from .admin_workspace import (
    correction_display,
    lifecycle_display,
    grand_final_policy_label,
    match_card,
    reset_final_changes_display,
    result_summary,
    round_label,
    series_label,
    workspace_url,
    swiss_workspace,
)

from .commands import (
    apply_correction,
    configure_elimination,
    create_competition,
    finalize_match,
    preview_correction,
    publish_draw,
    review_correction_preview,
    save_match_progress,
    save_elimination_draw,
    schedule_match,
    select_entrants,
    set_match_series_length,
    set_round_series_length,
    start_match,
)
from .forms import (
    CompetitionSetupForm,
    EntrantTransitionForm,
    CompetitionEndForm,
    LifecycleConfirmationForm,
    CorrectionReasonForm,
    DrawForm,
    EntrantSelectionForm,
    NewCompetitionForm,
    ProgressForm,
    RevisionForm,
    ResultForm,
    ScheduleForm,
    SeriesLengthForm,
    GroupDrawForm,
    TieReasonForm,
    QualificationTieForm,
    StageOrderForm,
    NextStageDrawForm,
    SwissRoundForm,
    SwissRematchForm,
)
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
    StageGroup,
)
from .round_robin_commands import (
    TIE_SALT,
    configure_round_robin,
    save_round_robin_draw,
    group_standings,
)
from .forms import TIEBREAK_CHOICES
from .stage_commands import (
    set_stage_groups,
    set_stage_advancement,
    reorder_stages,
    remove_stage,
    validate_stage_plan,
    validate_stage_field,
    _configured_incoming_count,
)
from .swiss_commands import (
    configure_swiss,
    save_swiss_draw,
    generate_swiss_round,
    publish_swiss_round,
)
from .handoff_commands import generate_next_stage_draw
from .qualification import (
    stage_qualification,
    preview_qualification_tie,
    confirm_qualification_tie,
)


from .lifecycle_commands import (
    preview_entrant_transition,
    apply_entrant_transition,
    preview_competition_end,
    apply_competition_end,
    preview_competition_reopen,
    apply_competition_reopen,
    review_lifecycle_preview,
)


def _selected_stage(request, competition):
    if request.GET.get("stage"):
        if not request.GET["stage"].isdecimal():
            raise Http404
        return get_object_or_404(competition.stages, pk=request.GET["stage"])
    return competition.stages.select_related("champion").first()


def _stage_context_id(request, stage):
    return (
        stage.pk
        if stage and (request.GET.get("stage") or stage.competition.stages.count() > 1)
        else None
    )


def _stage_action_url(url, stage_id):
    return f"{url}?stage={stage_id}" if stage_id is not None else url


class ImmutableInline:
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CompetitionEntrantInline(ImmutableInline, TabularInline):
    model = CompetitionEntrant
    readonly_fields = ("registration", "display_name", "display_tag", "status")


class StageInline(ImmutableInline, TabularInline):
    model = Stage
    readonly_fields = (
        "sequence",
        "name",
        "format",
        "series_mode",
        "default_series_length",
        "status",
        "champion",
        "published_at",
        "completed_at",
    )


def _action_response(request, *, title, form, opts, change_url, extra=None):
    extra = extra or {}
    if extra.get("impact"):
        extra["impact_display"] = correction_display(extra["impact"])
    return TemplateResponse(
        request,
        "admin/competitions/action_form.html",
        {
            **admin.site.each_context(request),
            "title": title,
            "form": form,
            "opts": opts,
            "change_url": change_url,
            "submit_label": title,
            **extra,
        },
    )


@admin.register(Competition)
class CompetitionAdmin(OrganizerStaffAdmin):
    list_display = ("competition_name", "stage_status", "updated_at")
    change_list_template = "admin/competitions/change_list.html"
    search_fields = (
        "tournament_game__tournament__name",
        "tournament_game__game__name",
    )
    list_select_related = ("tournament_game__tournament", "tournament_game__game")
    readonly_fields = (
        "tournament_game",
        "revision",
        "matches_link",
        "changes_link",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    inlines = (CompetitionEntrantInline, StageInline)
    actions_detail = (
        "configure_detail",
        "entrants_detail",
        "draw_detail",
        "publish_detail",
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request)

    def add_view(self, request, form_url="", extra_context=None):
        require_organizer(request.user, "competitions.add_competition")
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        form = NewCompetitionForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                competition = create_competition(
                    actor=request.user,
                    tournament_game_id=form.cleaned_data["tournament_game"].pk,
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return HttpResponseRedirect(workspace_url(competition.pk))
        return _action_response(
            request,
            title="Create competition",
            form=form,
            opts=self.model._meta,
            change_url=reverse("admin:competitions_competition_changelist"),
            extra={
                "description": "Choose a division, then set up its bracket.",
                "submit_label": "Continue to setup",
            },
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        competition = self.get_object(request, object_id)
        if competition is None:
            raise Http404
        if not self.has_view_or_change_permission(request, competition):
            raise PermissionDenied
        stage = _selected_stage(request, competition)
        draw = (
            stage.draws.exclude(state=StageDraw.State.SUPERSEDED).first()
            if stage
            else None
        )
        entrants = list(competition.entrants.filter(is_selected=True).order_by("pk"))
        published = bool(stage and stage.published_at)
        can_manage = (
            self.has_change_permission(request, competition)
            and not competition.ended_at
        )
        can_view_matches = admin.site.get_model_admin(Match).has_view_permission(
            request
        )
        can_operate = (
            not competition.ended_at
            and can_view_matches
            and request.user.has_perm("competitions.change_match")
        )
        can_view_changes = request.user.has_perm("competitions.view_changeset")
        selected_stage_id = _stage_context_id(request, stage)
        url = workspace_url(competition.pk, stage_id=selected_stage_id)
        selected_tab = request.GET.get("tab", "bracket" if draw else "setup")
        if selected_tab not in ("setup", "entrants", "bracket", "standings", "changes"):
            raise Http404
        if selected_tab == "changes" and not can_view_changes:
            raise PermissionDenied
        is_swiss = bool(
            stage
            and stage.format in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)
        )
        swiss_display = swiss_workspace(draw) if draw and is_swiss else None
        groups = list(draw.groups.all()) if draw else []
        selected_group = None
        if groups:
            requested = request.GET.get("group", str(groups[0].pk))
            selected_group = next((g for g in groups if str(g.pk) == requested), None)
            if selected_group is None:
                raise Http404
        steps = [
            (
                "Set up",
                "Name the stage and choose how many games decide a match.",
                "configure_detail",
                bool(stage),
            ),
            (
                "Choose entrants",
                "Select approved players or teams for this division.",
                "entrants_detail",
                len(entrants) >= 2,
            ),
            (
                "Seed the bracket",
                "Arrange entrants or shuffle once, then review the saved bracket.",
                "draw_detail",
                bool(draw),
            ),
            (
                "Publish",
                "Make the reviewed bracket visible and open match scoring.",
                "publish_detail",
                published,
            ),
        ]
        setup_steps = []
        next_step = next(
            (index for index, step in enumerate(steps) if not step[3]), None
        )
        for index, (label, description, action_name, done) in enumerate(steps):
            available = (
                can_manage
                and not published
                and (index == 0 or all(item[3] for item in steps[:index]))
            )
            setup_steps.append(
                {
                    "number": index + 1,
                    "label": label,
                    "description": description,
                    "url": _stage_action_url(
                        reverse(
                            f"admin:competitions_competition_{action_name}",
                            args=[competition.pk],
                        ),
                        selected_stage_id,
                    )
                    if available
                    else None,
                    "done": done,
                    "current": index == next_step,
                }
            )
        primary_action = (
            setup_steps[next_step] if next_step is not None and can_manage else None
        )
        entries = [
            {
                "seed": None,
                "name": item.display_name,
                "status": item.get_status_display(),
                "entrant": item,
            }
            for item in entrants
        ]
        rounds_by_section = {}
        all_cards = []
        round_choices = []
        selected_round_id = None
        if draw:
            entries = [
                {
                    "seed": item.seed,
                    "name": item.entrant.display_name,
                    "status": item.entrant.get_status_display(),
                    "entrant": item.entrant,
                }
                for item in draw.entries.select_related("entrant").order_by("seed")
            ]
        if draw and can_view_matches:
            slots = MatchSlot.objects.select_related(
                "entry__entrant", "resolved_entry__entrant", "source_match"
            )
            matches = Match.objects.select_related(
                "round__draw__stage__competition"
            ).prefetch_related(Prefetch("slots", queryset=slots))
            draw_rounds = list(
                draw.rounds.select_related(
                    "draw__stage", "tie_resolution"
                ).prefetch_related(Prefetch("matches", queryset=matches))
            )
            if selected_group:
                draw_rounds = [
                    r for r in draw_rounds if r.group_id == selected_group.pk
                ]
                round_choices = [
                    (r.pk, round_label(r, last_round_number=0)) for r in draw_rounds
                ]
                if round_choices:
                    requested = request.GET.get("round", str(round_choices[0][0]))
                    selected_round_id = next(
                        (pk for pk, _ in round_choices if str(pk) == requested), None
                    )
                    if selected_round_id is None:
                        raise Http404
            last_round_numbers = {}
            for round_ in draw_rounds:
                last_round_numbers[round_.section] = max(
                    round_.number, last_round_numbers.get(round_.section, 0)
                )
            for round_ in draw_rounds:
                cards = [
                    match_card(match, request.user) for match in round_.matches.all()
                ]
                all_cards.extend(cards)
                if selected_round_id is not None and round_.pk != selected_round_id:
                    continue
                rounds_by_section.setdefault(round_.section, []).append(
                    {
                        "id": round_.pk,
                        "label": round_label(
                            round_,
                            last_round_number=last_round_numbers[round_.section],
                        ),
                        "series_length": round_.series_length_override
                        or stage.default_series_length,
                        "series_label": series_label(
                            round_.series_mode_override or stage.series_mode,
                            round_.series_length_override
                            or stage.default_series_length,
                        ),
                        "resting_entries": [
                            e.entrant.display_name
                            for e in (
                                round_.tie_resolution.contenders.select_related(
                                    "entrant"
                                )
                                if round_.tie_resolution_id
                                else selected_group.entries.select_related("entrant")
                            )
                            if e.pk
                            not in {
                                s.resolved_entry_id
                                for m in round_.matches.all()
                                for s in m.slots.all()
                            }
                        ]
                        if selected_group
                        else [],
                        "state": round_.get_state_display(),
                        "series_url": reverse(
                            "admin:competitions_round_series_detail", args=[round_.pk]
                        )
                        if can_operate
                        and published
                        and round_.state == Round.State.PUBLISHED
                        and (
                            not round_.tie_resolution_id
                            or round_.tie_resolution.state != "SUPERSEDED"
                        )
                        and not any(
                            match.started_at and match.series_length_override is None
                            for match in round_.matches.all()
                        )
                        else None,
                        "matches": cards,
                    }
                )
            if published:
                primary_action = next(
                    (
                        {
                            "url": card["result_url"],
                            "label": f"Enter result: {card['title']}",
                        }
                        for card in all_cards
                        if card["result_url"] and card["result_label"] == "Enter result"
                    ),
                    None,
                )
        changes_page = None
        group_display = None
        if selected_group:
            state = group_standings(selected_group)
            entry_names = dict(
                selected_group.entries.values_list("pk", "entrant__display_name")
            )
            tied_ids = {pk for tie in state["cutoff_ties"] for pk in tie["entry_ids"]}
            group_display = {
                "group": selected_group,
                "state": state["qualification_state"],
                "rows": [
                    {
                        "row": row,
                        "name": entry_names[row.entry_id],
                        "qualification": "Provisional"
                        if state["qualification_state"] == "PROVISIONAL"
                        else "Qualified"
                        if row.entry_id in state["qualifiers"]
                        else "Tied"
                        if row.entry_id in tied_ids
                        else "Not qualified",
                    }
                    for row in state["standings"]
                ],
                "qualifiers": [entry_names[pk] for pk in state["qualifiers"]],
                "tie_url": reverse(
                    "admin:competitions_group_tie_preview", args=[selected_group.pk]
                )
                if can_manage
                and published
                and any(t["resolution_id"] is None for t in state["cutoff_ties"])
                else None,
                "resolutions": selected_group.tie_resolutions.all(),
            }
        if selected_tab == "changes":
            changes_page = Paginator(
                competition.changes.select_related("actor").order_by("-revision"), 25
            ).get_page(request.GET.get("page"))
            changes_page.object_list = [
                {
                    "created_at": change.created_at,
                    "label": change.kind.replace("_", " ").capitalize(),
                    "actor": str(change.actor) if change.actor else "System",
                    "internal_reason": change.internal_reason,
                    "before": result_summary(change.private_data.get("before")),
                    "after": result_summary(
                        change.private_data.get("after")
                        or change.public_data.get("after")
                        or (
                            change.public_data
                            if "side_one_score" in change.public_data
                            else None
                        )
                    ),
                    "resets": [
                        result_summary(item)
                        for item in change.private_data.get("reset_matches", [])
                    ],
                    "activation_changes": reset_final_changes_display(
                        change.private_data.get("reset_final_changes", [])
                    ),
                    "url": reverse(
                        "admin:competitions_match_change",
                        args=[change.private_data["match_id"]],
                    )
                    if change.private_data.get("match_id") and can_view_matches
                    else None,
                }
                for change in changes_page
            ]
        stages = list(competition.stages.prefetch_related("group_plans"))
        plan_locked = bool(stages and stages[0].published_at)
        plan_error = None
        plan_rows = []
        for item in stages:
            saved_draw = item.draws.exclude(state="SUPERSEDED").first()
            incoming = (
                saved_draw.entries.count()
                if saved_draw
                else (_configured_incoming_count(competition, item.sequence) or None)
            )
            saved_groups = list(saved_draw.groups.all()) if saved_draw else []
            outgoing = (
                sum(p.qualifying_places for p in item.group_plans.all())
                if item.format == "ROUND_ROBIN"
                else None
                if item.format == Stage.Format.SWISS_THRESHOLD
                else item.advancement_count
            )
            plan_rows.append(
                {
                    "stage": item,
                    "groups": [
                        {
                            "name": group.name,
                            "size": group.entries.count(),
                            "qualifying_places": group.qualifying_places,
                        }
                        for group in saved_groups
                    ]
                    if saved_groups
                    else list(item.group_plans.all()),
                    "incoming_count": incoming,
                    "outgoing_count": outgoing if item.sequence < len(stages) else None,
                    "configure_url": _stage_action_url(
                        reverse(
                            "admin:competitions_competition_configure_detail",
                            args=[competition.pk],
                        ),
                        item.pk,
                    ),
                    "remove_url": reverse(
                        "admin:competitions_stage_remove",
                        args=[competition.pk, item.pk],
                    )
                    if not item.draws.exists()
                    else None,
                }
            )
            incoming = outgoing
        try:
            validate_stage_plan(competition)
        except ValidationError as error:
            plan_error = " ".join(error.messages)
        qualification = (
            stage_qualification(draw) if draw and draw.state == "PUBLISHED" else None
        )
        entry_names = (
            dict(draw.entries.values_list("pk", "entrant__display_name"))
            if draw
            else {}
        )
        qualification_display = (
            {
                **qualification,
                "qualifier_names": [
                    entry_names[i] for i in qualification["qualifier_entry_ids"]
                ],
                "placement_names": [
                    [entry_names[i] for i in band] for band in qualification["bands"]
                ],
            }
            if qualification
            else None
        )
        waiting_reason = None
        if stage and stage.sequence > 1 and not draw:
            previous = competition.stages.get(sequence=stage.sequence - 1)
            source = previous.draws.filter(state="PUBLISHED").first()
            source_qualification = stage_qualification(source) if source else None
            if (
                source_qualification
                and source_qualification["qualification_state"] == "RESOLVED"
            ):
                try:
                    validate_stage_field(
                        stage, len(source_qualification["qualifier_entry_ids"])
                    )
                except ValidationError as error:
                    waiting_reason = " ".join(error.messages)
                    primary_action = None
                else:
                    waiting_reason = "Ready for a saved random draw"
            else:
                waiting_reason = (
                    source_qualification["block_reason"]
                    if source_qualification
                    else None
                ) or "Waiting for previous stage"
            if can_manage and waiting_reason == "Ready for a saved random draw":
                primary_action = {
                    "url": reverse(
                        "admin:competitions_stage_generate",
                        args=[competition.pk, stage.pk],
                    ),
                    "label": "Generate next stage draw",
                }
        if stage and stage.sequence > 1:
            setup_steps[1]["url"] = None
            setup_steps[2]["url"] = (
                reverse(
                    "admin:competitions_stage_generate", args=[competition.pk, stage.pk]
                )
                if can_manage
                and (not draw or draw.state == "DRAFT")
                and (
                    draw is not None
                    or waiting_reason == "Ready for a saved random draw"
                )
                else None
            )
        if plan_locked:
            setup_steps[0]["url"] = None
            setup_steps[1]["url"] = None
        if draw and draw.state == "DRAFT" and can_manage:
            primary_action = {
                "url": _stage_action_url(
                    reverse(
                        "admin:competitions_competition_publish_detail",
                        args=[competition.pk],
                    ),
                    selected_stage_id,
                ),
                "label": "Publish saved draw",
            }
        if swiss_display and can_manage and draw.state == StageDraw.State.PUBLISHED:
            if (
                swiss_display["round"]
                and swiss_display["round"].state == Round.State.DRAFT
            ):
                primary_action = {
                    "label": "Publish saved Swiss round",
                    "url": reverse(
                        "admin:competitions_swiss_publish",
                        args=[competition.pk, stage.pk],
                    ),
                }
            elif swiss_display["can_generate"]:
                primary_action = {
                    "label": "Generate next Swiss round",
                    "url": reverse(
                        "admin:competitions_swiss_generate",
                        args=[competition.pk, stage.pk],
                    ),
                }
        for entry in entries:
            entry["transition_url"] = (
                reverse(
                    "admin:competitions_entrant_transition",
                    args=[competition.pk, entry["entrant"].pk],
                )
                if can_manage
                else None
            )
        return TemplateResponse(
            request,
            "admin/competitions/workspace.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "original": competition,
                "title": f"{competition.tournament_game.tournament.name} · {competition.tournament_game.game.name}",
                "competition": competition,
                "end_url": reverse(
                    "admin:competitions_competition_end",
                    args=[competition.pk, stage.pk],
                )
                if can_manage and stage and stage.published_at
                else None,
                "reopen_url": reverse(
                    "admin:competitions_competition_reopen", args=[competition.pk]
                )
                if competition.ended_at
                and self.has_change_permission(request, competition)
                and request.user.has_perm("competitions.change_match")
                else None,
                "stage": stage,
                "swiss_display": swiss_display,
                "swiss_generate_url": reverse(
                    "admin:competitions_swiss_generate", args=[competition.pk, stage.pk]
                )
                if is_swiss and can_manage and draw and draw.state == "PUBLISHED"
                else None,
                "selected_stage_id": selected_stage_id,
                "stages": stages,
                "plan_rows": plan_rows,
                "plan_locked": plan_locked,
                "plan_error": plan_error,
                "waiting_reason": waiting_reason,
                "qualification_display": qualification_display,
                "qualification_tie_url": reverse(
                    "admin:competitions_draw_tie_preview", args=[draw.pk]
                )
                if draw
                and can_manage
                and qualification
                and any(
                    t["resolution_id"] is None and t["group_id"] is None
                    for t in qualification["cutoffs"]
                )
                else None,
                "add_stage_url": reverse(
                    "admin:competitions_competition_configure_detail",
                    args=[competition.pk],
                )
                + f"?sequence={len(stages) + 1}",
                "reorder_url": reverse(
                    "admin:competitions_stages_order", args=[competition.pk]
                ),
                "grand_final_policy": grand_final_policy_label(stage),
                "stage_series_label": series_label(
                    stage.series_mode, stage.default_series_length
                )
                if stage
                else "",
                "rule_labels": [
                    dict(TIEBREAK_CHOICES)[rule] for rule in stage.tiebreaks
                ]
                if stage
                else [],
                "groups": groups,
                "round_choices": round_choices,
                "selected_round_id": selected_round_id,
                "selected_group": selected_group,
                "group_display": group_display,
                "draw": draw,
                "workspace_url": url,
                "group_base_url": workspace_url(
                    competition.pk, selected_tab, stage_id=selected_stage_id
                ),
                "bracket_url": workspace_url(
                    competition.pk, "bracket", stage_id=selected_stage_id
                ),
                "setup_url": workspace_url(
                    competition.pk, "setup", stage_id=selected_stage_id
                ),
                "tab": selected_tab,
                "tabs": [
                    {
                        "label": label,
                        "url": workspace_url(
                            competition.pk, tab, stage_id=selected_stage_id
                        ),
                        "active": tab == selected_tab,
                    }
                    for tab, label in [
                        ("bracket", "Bracket & matches"),
                        ("standings", "Standings"),
                        ("entrants", "Entrants"),
                        ("setup", "Setup"),
                        ("changes", "Changes"),
                    ]
                    if (tab != "changes" or can_view_changes)
                    and (
                        tab != "standings"
                        or groups
                        or is_swiss
                        or (stage and stage.advancement_count)
                    )
                ],
                "can_manage": can_manage,
                "can_view_matches": can_view_matches,
                "primary_action": primary_action,
                "setup_steps": setup_steps,
                "entrants_url": setup_steps[1]["url"],
                "entries": entries,
                "bracket_sections": [
                    {
                        "kind": section,
                        "rounds": rounds_by_section[section],
                    }
                    for section in Round.Section
                    if section in rounds_by_section
                ],
                "participant_count": len(entries),
                "completed_count": sum(
                    card["status"] in ("Completed", "Bye", "No contest")
                    for card in all_cards
                ),
                "total_count": len(all_cards),
                "changes_page": changes_page,
                "public_url": f"{settings.UNFOLD.get('SITE_URL', '').rstrip('/')}/tournaments/{competition.tournament_game.tournament.slug}/games/{competition.tournament_game_id}/bracket"
                if published and competition.tournament_game.tournament.is_published
                else None,
            },
        )

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(
        description="Competition", ordering="tournament_game__tournament__name"
    )
    def competition_name(self, obj):
        return (
            f"{obj.tournament_game.tournament.name} · {obj.tournament_game.game.name}"
        )

    @admin.display(description="Stage status")
    def stage_status(self, obj):
        stage = obj.stages.order_by("sequence").first()
        return stage.get_status_display() if stage else "Not configured"

    @admin.display(description="Matches")
    def matches_link(self, obj):
        return format_html(
            '<a href="{}">Open matches</a>',
            reverse("admin:competitions_match_changelist")
            + f"?round__draw__stage__competition__id__exact={obj.pk}",
        )

    @admin.display(description="Changes")
    def changes_link(self, obj):
        return format_html(
            '<a href="{}">Open Changes</a>',
            reverse("admin:competitions_changeset_changelist")
            + f"?competition__id__exact={obj.pk}",
        )

    def _plan_stage(self, request, competition_id, stage_id):
        require_organizer(request.user, "competitions.change_competition")
        competition = get_object_or_404(Competition, pk=competition_id)
        stage = get_object_or_404(competition.stages, pk=stage_id)
        return competition, stage

    def stage_rules_view(self, request, competition_id, stage_id):
        competition, stage = self._plan_stage(request, competition_id, stage_id)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        return HttpResponseRedirect(
            _stage_action_url(
                reverse(
                    "admin:competitions_competition_configure_detail",
                    args=[competition.pk],
                ),
                stage.pk,
            )
        )

    def stage_generate_view(self, request, competition_id, stage_id):
        competition, stage = self._plan_stage(request, competition_id, stage_id)
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        form = NextStageDrawForm(
            request.POST if request.method == "POST" else None,
            initial={"expected_revision": competition.revision},
        )
        if request.method == "POST" and form.is_valid():
            try:
                generate_next_stage_draw(
                    actor=request.user, stage_id=stage.pk, **form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return HttpResponseRedirect(
                    workspace_url(competition.pk, "bracket", stage_id=stage.pk)
                )
        return _action_response(
            request,
            title="Generate next stage draw",
            form=form,
            opts=self.model._meta,
            change_url=workspace_url(competition.pk, "bracket", stage_id=stage.pk),
            extra={
                "description": "Finish all required previous-stage play and qualification cutoffs. Save one unrestricted random draw, review it, then publish separately.",
                "submit_label": "Generate and preview draw",
            },
        )

    def swiss_generate_view(self, request, competition_id, stage_id):
        return self._swiss_round_view(
            request, competition_id, stage_id, action="generate"
        )

    def swiss_publish_view(self, request, competition_id, stage_id):
        return self._swiss_round_view(
            request, competition_id, stage_id, action="publish"
        )

    def swiss_rematch_view(self, request, competition_id, stage_id):
        return self._swiss_round_view(
            request, competition_id, stage_id, action="rematch"
        )

    def _swiss_round_view(self, request, competition_id, stage_id, *, action):
        competition, stage = self._plan_stage(request, competition_id, stage_id)
        if stage.format not in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
            raise Http404
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        token = (
            request.POST.get("token", "")
            if request.method == "POST"
            else request.GET.get("token", "")
        )
        intent = None
        if action == "rematch":
            try:
                intent = signing.loads(
                    token, salt="competitions.swiss_rematch", max_age=3600
                )
            except signing.BadSignature as error:
                raise PermissionDenied(
                    "Generate a round without rematches first."
                ) from error
            if (
                intent.get("stage_id") != stage.pk
                or intent.get("revision") != competition.revision
                or intent.get("actor_id") != request.user.pk
            ):
                raise PermissionDenied(
                    "This rematch review expired. Refresh and generate without rematches again."
                )
        form_class = (
            SwissRematchForm
            if action == "rematch"
            else SwissRoundForm
            if action == "generate"
            else RevisionForm
        )
        form = form_class(
            request.POST if request.method == "POST" else None,
            initial={"expected_revision": competition.revision},
        )
        extra = {"token": token if intent else None}
        if request.method == "POST" and form.is_valid():
            try:
                revision = form.cleaned_data["expected_revision"]
                if action == "publish":
                    round_ = Round.objects.filter(
                        draw__stage=stage,
                        draw__state="PUBLISHED",
                        state="DRAFT",
                        section="NORMAL",
                    ).first()
                    if not round_:
                        raise ValidationError(
                            "Generate a private Swiss preview before publishing it."
                        )
                    publish_swiss_round(
                        actor=request.user,
                        round_id=round_.pk,
                        expected_revision=revision,
                    )
                else:
                    generate_swiss_round(
                        actor=request.user,
                        stage_id=stage.pk,
                        expected_revision=revision,
                        regenerate=intent["regenerate"]
                        if intent
                        else form.cleaned_data["regenerate"],
                        allow_rematches=action == "rematch",
                        internal_reason=form.cleaned_data.get("internal_reason", ""),
                    )
            except ValidationError as error:
                form.add_error(None, error)
                if action == "generate" and error.messages == [
                    "No complete Swiss round is possible without a confirmed rematch exception."
                ]:
                    rematch_token = signing.dumps(
                        {
                            "stage_id": stage.pk,
                            "revision": revision,
                            "actor_id": request.user.pk,
                            "regenerate": form.cleaned_data["regenerate"],
                        },
                        salt="competitions.swiss_rematch",
                    )
                    extra.update(
                        rematch_token=rematch_token,
                        rematch_url=reverse(
                            "admin:competitions_swiss_rematch",
                            args=[competition.pk, stage.pk],
                        )
                        + "?"
                        + urlencode({"token": rematch_token}),
                    )
            else:
                return HttpResponseRedirect(
                    workspace_url(competition.pk, "bracket", stage_id=stage.pk)
                )
        title = {
            "generate": "Generate next Swiss round",
            "publish": "Publish saved Swiss round",
            "rematch": "Allow required rematches",
        }[action]
        return _action_response(
            request,
            title=title,
            form=form,
            opts=self.model._meta,
            change_url=workspace_url(competition.pk, "bracket", stage_id=stage.pk),
            extra={
                **extra,
                "description": "Review the saved private pairings, then publish separately. Publication validates the recorded rematch authorization.",
                "submit_label": title,
            },
        )

    def stage_remove_view(self, request, competition_id, stage_id):
        competition, stage = self._plan_stage(request, competition_id, stage_id)
        return self._competition_form_view(
            request,
            competition_id,
            title=f"Remove unused stage: {stage.name}",
            form_class=RevisionForm,
            stage=stage,
            command=lambda item, revision, data: remove_stage(
                actor=request.user, stage_id=stage.pk, expected_revision=revision
            ),
        )

    def stages_order_view(self, request, competition_id):
        require_organizer(request.user, "competitions.change_competition")
        competition = get_object_or_404(Competition, pk=competition_id)
        return self._competition_form_view(
            request,
            competition_id,
            title="Reorder stages",
            form_class=StageOrderForm,
            form_kwargs={"competition": competition},
            command=lambda item, revision, data: reorder_stages(
                actor=request.user,
                competition_id=item.pk,
                expected_revision=revision,
                stage_ids=data["stage_ids"],
            ),
        )

    def draw_tie_preview_view(self, request, draw_id):
        draw = get_object_or_404(
            StageDraw.objects.select_related("stage__competition"), pk=draw_id
        )
        return self._tie_preview_view(request, draw)

    def draw_tie_confirm_view(self, request, draw_id):
        draw = get_object_or_404(
            StageDraw.objects.select_related("stage__competition"), pk=draw_id
        )
        return self._tie_confirm_view(request, draw)

    def entrant_transition_view(self, request, competition_id, entrant_id):
        competition = get_object_or_404(Competition, pk=competition_id)
        entrant = get_object_or_404(competition.entrants, pk=entrant_id)
        return self._lifecycle_view(
            request, competition, "entrant_transition", entrant=entrant
        )

    def competition_end_view(self, request, competition_id, stage_id):
        competition = get_object_or_404(Competition, pk=competition_id)
        stage = get_object_or_404(competition.stages, pk=stage_id)
        return self._lifecycle_view(
            request, competition, "competition_end", stage=stage
        )

    def competition_reopen_view(self, request, competition_id):
        competition = get_object_or_404(Competition, pk=competition_id)
        return self._lifecycle_view(request, competition, "competition_reopen")

    def _lifecycle_view(self, request, competition, kind, *, entrant=None, stage=None):
        require_organizer(request.user, "competitions.change_competition")
        if kind == "competition_reopen":
            require_organizer(request.user, "competitions.change_match")
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        titles = {
            "entrant_transition": "Change entrant availability",
            "competition_end": "End competition",
            "competition_reopen": "Reopen competition",
        }
        title = titles[kind]
        token = request.POST.get("token") if request.method == "POST" else None
        impact = None
        form_class = (
            EntrantTransitionForm
            if entrant
            else CompetitionEndForm
            if stage
            else RevisionForm
        )
        form = form_class(
            request.POST if request.method == "POST" else None,
            initial={
                "expected_revision": competition.revision,
                **({"status": entrant.status} if entrant else {}),
            },
        )
        if token:
            try:
                impact = review_lifecycle_preview(actor=request.user, token=token)
                if (
                    impact["kind"]
                    not in (
                        {
                            "entrant_withdrawn",
                            "entrant_disqualified",
                            "entrant_restored",
                            "entrant_status_changed",
                        }
                        if entrant
                        else {"competition_ended"}
                        if stage
                        else {"competition_reopened"}
                    )
                    or impact["competition_id"] != competition.pk
                    or (entrant and impact.get("entrant_id") != entrant.pk)
                    or (stage and impact.get("stage_id") != stage.pk)
                ):
                    raise ValidationError(
                        "This preview belongs to a different operation or subject."
                    )
            except (PermissionDenied, ValidationError) as error:
                impact = None
                form = LifecycleConfirmationForm(request.POST)
                form.add_error(None, error)
            else:
                form = LifecycleConfirmationForm(request.POST, impact=impact)
                if form.is_valid():
                    data = form.cleaned_data
                    try:
                        common = dict(
                            actor=request.user,
                            token=token,
                            internal_reason=data["internal_reason"],
                            confirm_resets=data.get("confirm_resets", False),
                        )
                        if entrant:
                            apply_entrant_transition(
                                **common,
                                confirm_live_forfeits=data.get(
                                    "confirm_live_forfeits", False
                                ),
                            )
                        elif stage:
                            apply_competition_end(**common)
                        else:
                            apply_competition_reopen(**common)
                    except (PermissionDenied, ValidationError) as error:
                        form.add_error(None, error)
                    else:
                        self.message_user(
                            request, f"{title} completed.", messages.SUCCESS
                        )
                        return HttpResponseRedirect(
                            workspace_url(
                                competition.pk, "entrants" if entrant else None
                            )
                        )
        elif request.method == "POST" and form.is_valid():
            try:
                common = dict(
                    actor=request.user,
                    expected_revision=form.cleaned_data["expected_revision"],
                )
                if entrant:
                    impact = preview_entrant_transition(
                        **common,
                        entrant_id=entrant.pk,
                        status=form.cleaned_data["status"],
                    )
                elif stage:
                    impact = preview_competition_end(
                        **common,
                        stage_id=stage.pk,
                        award_sole_survivor=form.cleaned_data["award_sole_survivor"],
                    )
                else:
                    impact = preview_competition_reopen(
                        **common, competition_id=competition.pk
                    )
            except (PermissionDenied, ValidationError) as error:
                form.add_error(None, error)
            else:
                token = impact["token"]
                form = LifecycleConfirmationForm(impact=impact)
        return _action_response(
            request,
            title=title,
            form=form,
            opts=self.model._meta,
            change_url=workspace_url(competition.pk),
            extra={
                "workspace_url": workspace_url(competition.pk),
                "token": token,
                "description": f"{entrant.display_name} · Current status: {entrant.get_status_display()}"
                if entrant
                else "Reopening keeps retired fixtures historical. Generate fresh replacement previews and explicitly publish them."
                if kind == "competition_reopen"
                else "End only when the locked continuation is impossible. Source results remain recorded.",
                "lifecycle_impact": impact,
                "lifecycle_display": lifecycle_display(
                    impact, competition, request.user
                )
                if impact
                else None,
                "submit_label": "Confirm lifecycle change"
                if impact
                else "Preview impact",
            },
        )

    def get_urls(self):
        return [
            path(
                "<int:competition_id>/entrant/<int:entrant_id>/transition/",
                self.admin_site.admin_view(self.entrant_transition_view),
                name="competitions_entrant_transition",
            ),
            path(
                "<int:competition_id>/stage/<int:stage_id>/end/",
                self.admin_site.admin_view(self.competition_end_view),
                name="competitions_competition_end",
            ),
            path(
                "<int:competition_id>/reopen/",
                self.admin_site.admin_view(self.competition_reopen_view),
                name="competitions_competition_reopen",
            ),
            path(
                "<int:competition_id>/stage/<int:stage_id>/swiss/generate/",
                self.admin_site.admin_view(self.swiss_generate_view),
                name="competitions_swiss_generate",
            ),
            path(
                "<int:competition_id>/stage/<int:stage_id>/swiss/publish/",
                self.admin_site.admin_view(self.swiss_publish_view),
                name="competitions_swiss_publish",
            ),
            path(
                "<int:competition_id>/stage/<int:stage_id>/swiss/rematch/",
                self.admin_site.admin_view(self.swiss_rematch_view),
                name="competitions_swiss_rematch",
            ),
            path(
                "<int:competition_id>/stage/<int:stage_id>/rules/",
                self.admin_site.admin_view(self.stage_rules_view),
                name="competitions_stage_rules",
            ),
            path(
                "<int:competition_id>/stage/<int:stage_id>/generate/",
                self.admin_site.admin_view(self.stage_generate_view),
                name="competitions_stage_generate",
            ),
            path(
                "<int:competition_id>/stage/<int:stage_id>/remove/",
                self.admin_site.admin_view(self.stage_remove_view),
                name="competitions_stage_remove",
            ),
            path(
                "<int:competition_id>/stages/order/",
                self.admin_site.admin_view(self.stages_order_view),
                name="competitions_stages_order",
            ),
            path(
                "draw/<int:draw_id>/tie/preview/",
                self.admin_site.admin_view(self.draw_tie_preview_view),
                name="competitions_draw_tie_preview",
            ),
            path(
                "draw/<int:draw_id>/tie/confirm/",
                self.admin_site.admin_view(self.draw_tie_confirm_view),
                name="competitions_draw_tie_confirm",
            ),
            path(
                "group/<int:group_id>/tie/preview/",
                self.admin_site.admin_view(self.group_tie_preview_view),
                name="competitions_group_tie_preview",
            ),
            path(
                "group/<int:group_id>/tie/confirm/",
                self.admin_site.admin_view(self.group_tie_confirm_view),
                name="competitions_group_tie_confirm",
            ),
            path(
                "create/<int:division_id>/",
                self.admin_site.admin_view(self.create_view),
                name="competitions_competition_create_for_division",
            ),
        ] + super().get_urls()

    def group_tie_preview_view(self, request, group_id):
        require_organizer(request.user, "competitions.change_competition")
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        group = get_object_or_404(
            StageGroup.objects.select_related("draw__stage__competition"), pk=group_id
        )
        return self._tie_preview_view(request, group.draw, group)

    def _tie_preview_view(self, request, draw, group=None):
        require_organizer(request.user, "competitions.change_competition")
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        form = QualificationTieForm(
            request.POST if request.method == "POST" else None,
            group=group,
            draw=draw,
            initial={"expected_revision": draw.stage.competition.revision},
        )
        extra = {
            "workspace_url": workspace_url(
                draw.stage.competition_id,
                "standings",
                stage_id=_stage_context_id(request, draw.stage),
            )
        }
        if request.method == "POST" and form.is_valid():
            try:
                data = form.cleaned_data
                preview = preview_qualification_tie(
                    actor=request.user,
                    draw_id=draw.pk,
                    group_id=group.pk if group else None,
                    **{
                        key: data[key]
                        for key in (
                            "expected_revision",
                            "tied_entry_ids",
                            "method",
                            "ordered_entry_ids",
                            "series_length",
                            "parent_resolution_id",
                        )
                    },
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                names = dict(draw.entries.values_list("pk", "entrant__display_name"))
                extra.update(
                    {
                        "token": preview["token"],
                        "form_action": reverse(
                            "admin:competitions_draw_tie_confirm", args=[draw.pk]
                        ),
                        "tie_preview": {
                            "group_name": group.name if group else draw.stage.name,
                            "method": preview["method"],
                            "places": preview["places"],
                            "ordered_entries": [
                                names[pk] for pk in preview["ordered_entry_ids"]
                            ],
                            "fixtures": [
                                [names[a], names[b]]
                                for r in preview["fixtures"]
                                for a, b in r["pairings"]
                            ],
                            "series_length": preview["series_length"],
                        },
                        "submit_label": "Confirm qualification tie",
                    }
                )
                return _action_response(
                    request,
                    title="Review qualification tie",
                    form=TieReasonForm(),
                    opts=self.model._meta,
                    change_url=extra["workspace_url"],
                    extra=extra,
                )
        return _action_response(
            request,
            title="Resolve qualification tie",
            form=form,
            opts=self.model._meta,
            change_url=extra["workspace_url"],
            extra={**extra, "submit_label": "Preview tie choice"},
        )

    def group_tie_confirm_view(self, request, group_id):
        group = get_object_or_404(
            StageGroup.objects.select_related("draw__stage__competition"), pk=group_id
        )
        return self._tie_confirm_view(request, group.draw, group)

    def _tie_confirm_view(self, request, draw, group=None):
        require_organizer(request.user, "competitions.change_competition")
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        form = TieReasonForm(request.POST)
        if form.is_valid():
            try:
                payload = signing.loads(
                    request.POST.get("token", ""), salt=TIE_SALT, max_age=3600
                )
                if payload.get("draw_id") != draw.pk or (
                    group and payload.get("group_id") != group.pk
                ):
                    raise ValidationError(
                        "This tie preview belongs to a different draw or group."
                    )
                confirm_qualification_tie(
                    actor=request.user,
                    token=request.POST.get("token", ""),
                    internal_reason=form.cleaned_data["internal_reason"],
                )
            except (ValidationError, signing.BadSignature) as error:
                form.add_error(None, str(error))
            else:
                return HttpResponseRedirect(
                    workspace_url(
                        draw.stage.competition_id,
                        "standings",
                        stage_id=_stage_context_id(request, draw.stage),
                    )
                )
        return _action_response(
            request,
            title="Confirm qualification tie",
            form=form,
            opts=self.model._meta,
            change_url=workspace_url(
                draw.stage.competition_id,
                "standings",
                stage_id=_stage_context_id(request, draw.stage),
            ),
            extra={"token": request.POST.get("token", "")},
        )

    def create_view(self, request, division_id):
        require_organizer(request.user, "competitions.add_competition")
        division = get_object_or_404(
            TournamentGame.objects.select_related("tournament", "game"), pk=division_id
        )
        existing = Competition.objects.filter(tournament_game_id=division_id).first()
        if existing:
            return HttpResponseRedirect(
                reverse("admin:competitions_competition_change", args=[existing.pk])
            )
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        form = forms.Form(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                competition = create_competition(
                    actor=request.user, tournament_game_id=division_id
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                self.message_user(request, "Competition created.", messages.SUCCESS)
                return HttpResponseRedirect(
                    reverse(
                        "admin:competitions_competition_change", args=[competition.pk]
                    )
                )
        return _action_response(
            request,
            title="Create competition",
            form=form,
            opts=self.model._meta,
            change_url=reverse(
                "admin:tournaments_tournamentgame_change", args=[division_id]
            ),
            extra={
                "description": f"Set up a bracket for {division.tournament.name} · {division.game.name}.",
                "submit_label": "Continue to setup",
            },
        )

    def _competition_form_view(
        self,
        request,
        object_id,
        *,
        title,
        form_class,
        command,
        form_kwargs=None,
        description=None,
        stage=None,
    ):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        competition = self.get_object(request, object_id)
        if competition is None:
            raise Http404
        stage = stage or _selected_stage(request, competition)
        selected_stage_id = _stage_context_id(request, stage)
        form_kwargs = {**(form_kwargs or {})}
        initial = {
            **(form_kwargs.pop("initial", None) or {}),
            "expected_revision": competition.revision,
        }
        form = form_class(
            request.POST if request.method == "POST" else None,
            initial=initial,
            **form_kwargs,
        )
        if (
            request.method == "POST"
            and not request.POST.get("preview_groups")
            and form.is_valid()
        ):
            try:
                data = form.cleaned_data.copy()
                command(competition, data.pop("expected_revision"), data)
            except (PermissionDenied, ValidationError) as error:
                form.add_error(None, error)
            else:
                self.message_user(request, f"{title} completed.", messages.SUCCESS)
                if (
                    selected_stage_id
                    and not competition.stages.filter(pk=selected_stage_id).exists()
                ):
                    selected_stage_id = None
                return HttpResponseRedirect(
                    workspace_url(competition.pk, stage_id=selected_stage_id)
                )
        return _action_response(
            request,
            title=title,
            form=form,
            opts=self.model._meta,
            change_url=workspace_url(competition.pk, stage_id=selected_stage_id),
            extra={
                "workspace_url": workspace_url(
                    competition.pk, stage_id=selected_stage_id
                ),
                "stage_setup": isinstance(form, CompetitionSetupForm),
                "group_plans": form.display_group_plans
                if isinstance(form, GroupDrawForm)
                else None,
                "description": description
                or f"{competition.tournament_game.tournament.name} · {competition.tournament_game.game.name}",
                "submit_label": {
                    "Stage setup": "Save setup",
                    "Select approved entrants": "Save entrants",
                    "Save bracket draw": "Save and preview bracket",
                    "Publish saved draw": "Publish bracket",
                }.get(title, title),
            },
        )

    @action(permissions=["change"], description="Stage setup")
    def configure_detail(self, request, object_id):
        competition = self.get_object(request, object_id)
        stage = _selected_stage(request, competition) if competition else None
        if request.GET.get("sequence"):
            stage = None
        initial = (
            {
                "stage_sequence": stage.sequence,
                "name": stage.name,
                "format": stage.format,
                "grand_final_policy": stage.grand_final_policy,
                "default_series_length": stage.default_series_length,
                "series_mode": stage.series_mode,
                "meetings": stage.round_robin_meetings,
                "win_points": stage.win_points,
                "draw_points": stage.draw_points,
                "loss_points": stage.loss_points,
                "advancement_count": stage.advancement_count,
                "round_policy": "CUSTOM"
                if stage.swiss_round_count is not None
                else "AUTOMATIC",
                "round_count": stage.swiss_round_count,
                "win_target": stage.swiss_win_target,
                "loss_limit": stage.swiss_loss_limit,
                **{
                    f"tiebreak_{i}": stage.tiebreaks[i - 1]
                    if i <= len(stage.tiebreaks)
                    else ""
                    for i in range(1, 5)
                },
            }
            if stage
            else {"stage_sequence": request.GET.get("sequence", 1)}
        )
        raw_sequence = str(initial["stage_sequence"])
        sequence = int(raw_sequence) if raw_sequence.isdecimal() else 1
        incoming = (
            _configured_incoming_count(competition, sequence) or None
            if competition
            else None
        )
        return self._competition_form_view(
            request,
            object_id,
            title="Stage setup",
            form_class=CompetitionSetupForm,
            form_kwargs={
                "initial": initial,
                "incoming_count": incoming,
                "is_final": not competition.stages.filter(
                    sequence__gt=sequence
                ).exists()
                if competition
                else True,
                "group_plans": list(stage.group_plans.all()) if stage else [],
            },
            command=lambda item, expected_revision, data: self._save_setup(
                request, item, expected_revision, data
            ),
        )

    @transaction.atomic
    def _save_setup(self, request, competition, expected_revision, data):
        if data["format"] in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
            command = configure_swiss
            fields = (
                "name",
                "format",
                "series_mode",
                "default_series_length",
                "round_count",
                "win_target",
                "loss_limit",
                "advancement_count",
                "win_points",
                "draw_points",
                "loss_points",
                "tiebreaks",
            )
        elif data["format"] == "ROUND_ROBIN":
            command = configure_round_robin
            fields = (
                "name",
                "meetings",
                "series_mode",
                "default_series_length",
                "win_points",
                "draw_points",
                "loss_points",
                "tiebreaks",
            )
        else:
            command = configure_elimination
            fields = ("name", "format", "grand_final_policy", "default_series_length")
        stage = command(
            actor=request.user,
            competition_id=competition.pk,
            expected_revision=expected_revision,
            stage_sequence=data["stage_sequence"] or 1,
            **{key: data[key] for key in fields},
        )
        competition.refresh_from_db(fields=("revision",))
        if data["format"] == "ROUND_ROBIN":
            saved = list(
                stage.group_plans.values_list("name", "size", "qualifying_places")
            )
            if saved != data["group_specs"]:
                set_stage_groups(
                    actor=request.user,
                    stage_id=stage.pk,
                    expected_revision=competition.revision,
                    group_specs=data["group_specs"],
                )
        elif (
            data["format"]
            not in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)
            and stage.advancement_count != data["advancement_count"]
        ):
            set_stage_advancement(
                actor=request.user,
                stage_id=stage.pk,
                expected_revision=competition.revision,
                advancement_count=data["advancement_count"],
            )
        return stage

    @action(permissions=["change"], description="Select approved entrants")
    def entrants_detail(self, request, object_id):
        competition = self.get_object(request, object_id)
        if competition is None:
            raise Http404
        initial = {
            "registrations": competition.entrants.filter(is_selected=True).values_list(
                "registration_id", flat=True
            )
        }
        return self._competition_form_view(
            request,
            object_id,
            title="Select approved entrants",
            form_class=EntrantSelectionForm,
            form_kwargs={"competition": competition, "initial": initial},
            command=lambda item, expected_revision, data: select_entrants(
                actor=request.user,
                competition_id=item.pk,
                expected_revision=expected_revision,
                registration_ids=[value.pk for value in data["registrations"]],
            ),
        )

    @action(permissions=["change"], description="Seed or randomize draw")
    def draw_detail(self, request, object_id):
        competition = self.get_object(request, object_id)
        if competition is None:
            raise Http404
        stage = _selected_stage(request, competition)
        if stage and stage.sequence > 1:
            return self.stage_generate_view(request, competition.pk, stage.pk)
        is_round_robin = stage and stage.format == "ROUND_ROBIN"
        is_swiss = stage and stage.format in (
            Stage.Format.SWISS_FIXED,
            Stage.Format.SWISS_THRESHOLD,
        )
        command = (
            save_round_robin_draw
            if is_round_robin
            else save_swiss_draw
            if is_swiss
            else save_elimination_draw
        )
        fields = (
            ("group_specs", "ordered_entrant_ids", "memberships", "randomize")
            if is_round_robin
            else ("entrant_order", "randomize")
        )
        return self._competition_form_view(
            request,
            object_id,
            title="Save bracket draw",
            form_class=GroupDrawForm if is_round_robin else DrawForm,
            form_kwargs={"competition": competition},
            command=lambda item, expected_revision, data: command(
                actor=request.user,
                competition_id=item.pk,
                expected_revision=expected_revision,
                **(
                    {
                        "ordered_entrant_ids": data.get("entrant_order"),
                        "randomized": data["randomize"],
                        "stage_id": stage.pk,
                    }
                    if is_swiss
                    else {key: data.get(key) for key in fields}
                ),
            ),
        )

    @action(permissions=["change"], description="Publish saved draw")
    def publish_detail(self, request, object_id):
        competition = self.get_object(request, object_id)
        stage = _selected_stage(request, competition) if competition else None
        policy = grand_final_policy_label(stage)
        return self._competition_form_view(
            request,
            object_id,
            title="Publish saved draw",
            form_class=RevisionForm,
            command=lambda item, expected_revision, data: publish_draw(
                actor=request.user,
                competition_id=item.pk,
                expected_revision=expected_revision,
                stage_id=stage.pk if stage else None,
            ),
            description=(
                f"{competition.tournament_game.tournament.name} · "
                f"{competition.tournament_game.game.name} · "
                f"{stage.get_format_display()}"
                + (f" · Grand final policy: {policy}" if policy else "")
                + " · First publication locks the whole stage plan: order, formats, group sizes and advancement rules."
                if competition and stage
                else None
            ),
        )


class ReadOnlyCompetitionAdmin(OrganizerStaffAdmin):
    def get_model_perms(self, request):
        # Keep guarded detail URLs, but navigate through the competition workspace.
        return {}

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(Stage)
class StageAdmin(ReadOnlyCompetitionAdmin):
    list_display = ("name", "competition", "format", "status", "published_at")
    list_filter = ("format", "status")


@admin.register(StageDraw)
class StageDrawAdmin(ReadOnlyCompetitionAdmin):
    list_display = ("stage", "version", "state", "randomized", "published_at")
    list_filter = ("state", "randomized")


@admin.register(StageEntry)
class StageEntryAdmin(ReadOnlyCompetitionAdmin):
    list_display = ("draw", "seed", "entrant")


@admin.register(Round)
class RoundAdmin(ReadOnlyCompetitionAdmin):
    list_display = ("draw", "number", "section", "series_length_override")
    actions_detail = ("series_detail",)

    def has_operate_permission(self, request, obj=None):
        return is_organizer_staff(request.user) and request.user.has_perm(
            "competitions.change_match"
        )

    def get_actions_detail(self, request, object_id):
        round_ = self.get_object(request, object_id)
        if (
            round_ is None
            or round_.draw.stage.competition.ended_at
            or round_.state == Round.State.SUPERSEDED
            or round_.draw.state == StageDraw.State.SUPERSEDED
        ):
            return []
        return super().get_actions_detail(request, object_id)

    @action(permissions=["operate"], description="Set series length")
    def series_detail(self, request, object_id):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        round_ = self.get_object(request, object_id)
        if round_ is None:
            raise Http404
        form = SeriesLengthForm(
            request.POST if request.method == "POST" else None,
            initial={
                "series_length": round_.series_length_override,
                "expected_revision": round_.draw.stage.competition.revision,
            },
            mode=round_.series_mode_override or round_.draw.stage.series_mode,
        )
        if request.method == "POST" and form.is_valid():
            try:
                set_round_series_length(
                    actor=request.user,
                    round_id=round_.pk,
                    expected_revision=form.cleaned_data["expected_revision"],
                    series_length=form.cleaned_data["series_length"],
                )
            except (PermissionDenied, ValidationError) as error:
                form.add_error(None, error)
            else:
                self.message_user(
                    request, "Set round series length completed.", messages.SUCCESS
                )
                return HttpResponseRedirect(
                    workspace_url(
                        round_.draw.stage.competition_id,
                        "bracket",
                        stage_id=_stage_context_id(request, round_.draw.stage),
                    )
                )
        return _action_response(
            request,
            title="Set round series length",
            form=form,
            opts=self.model._meta,
            change_url=workspace_url(
                round_.draw.stage.competition_id,
                "bracket",
                stage_id=_stage_context_id(request, round_.draw.stage),
            ),
            extra={
                "workspace_url": workspace_url(
                    round_.draw.stage.competition_id,
                    stage_id=_stage_context_id(request, round_.draw.stage),
                ),
                "description": f"Round {round_.number}",
                "submit_label": "Save series length",
            },
        )


class MatchSlotInline(ImmutableInline, TabularInline):
    model = MatchSlot
    fk_name = "match"
    readonly_fields = (
        "position",
        "entry",
        "source_match",
        "is_empty",
        "is_resolved",
        "resolved_entry",
    )


@admin.register(Match)
class MatchAdmin(ReadOnlyCompetitionAdmin):
    list_display = (
        "code",
        "stage_name",
        "round_number",
        "status",
        "scheduled_at",
        "winner",
    )
    list_filter = ("status", "round__draw__stage")
    search_fields = ("code",)
    inlines = (MatchSlotInline,)
    actions_detail = (
        "schedule_detail",
        "series_detail",
        "start_detail",
        "progress_detail",
        "finalize_detail",
        "correct_detail",
    )

    @admin.display(description="Stage")
    def stage_name(self, obj):
        return obj.round.draw.stage.name

    @admin.display(description="Round")
    def round_number(self, obj):
        return obj.round.number

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "round__draw__stage__competition__tournament_game__tournament",
                "round__draw__stage__competition__tournament_game__game",
                "winner__entrant",
            )
            .prefetch_related(
                Prefetch(
                    "slots",
                    queryset=MatchSlot.objects.select_related(
                        "resolved_entry__entrant", "entry__entrant", "source_match"
                    ),
                )
            )
        )

    def has_correct_permission(self, request, obj=None):
        return self.has_change_permission(request, obj) and request.user.has_perm(
            "competitions.change_competition"
        )

    def _match_context(self, request, match):
        card = match_card(match, request.user)
        actions = (
            self.get_actions_detail(request, str(match.pk))
            if card["can_operate"]
            else []
        )
        return {
            "workspace_url": workspace_url(
                match.round.draw.stage.competition_id,
                "bracket",
                stage_id=_stage_context_id(request, match.round.draw.stage),
            ),
            "bracket_url": workspace_url(
                match.round.draw.stage.competition_id,
                "bracket",
                stage_id=_stage_context_id(request, match.round.draw.stage),
            ),
            "setup_url": workspace_url(
                match.round.draw.stage.competition_id,
                "setup",
                stage_id=_stage_context_id(request, match.round.draw.stage),
            ),
            "match_card": card,
            "match_actions": [
                {
                    "label": item.description,
                    "url": reverse(f"admin:{item.action_name}", args=[match.pk]),
                }
                for item in actions
                if reverse(f"admin:{item.action_name}", args=[match.pk])
                != card["result_url"]
            ],
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        match = self.get_object(request, object_id)
        if match is None:
            raise Http404
        if not self.has_view_or_change_permission(request, match):
            raise PermissionDenied
        context = self._match_context(request, match)
        return TemplateResponse(
            request,
            "admin/competitions/match_detail.html",
            {
                **self.admin_site.each_context(request),
                **context,
                "title": context["match_card"]["title"],
                "opts": self.model._meta,
                "original": match,
                "changes_url": workspace_url(
                    match.round.draw.stage.competition_id,
                    "changes",
                    stage_id=_stage_context_id(request, match.round.draw.stage),
                )
                if request.user.has_perm("competitions.view_changeset")
                else None,
            },
        )

    def get_actions_detail(self, request, object_id):
        actions = super().get_actions_detail(request, object_id)
        match = self.get_object(request, object_id)
        if match is None:
            return []
        if (
            match.round.draw.stage.competition.ended_at
            or match.round.draw.state != StageDraw.State.PUBLISHED
        ):
            return []
        if (
            match.round.tie_resolution_id
            and match.round.tie_resolution.state == "SUPERSEDED"
        ):
            return []
        valid = {
            Match.Status.PENDING: {
                "schedule_detail",
                "series_detail",
                "start_detail",
                "progress_detail",
                "finalize_detail",
            },
            Match.Status.LIVE: {"progress_detail", "finalize_detail"},
            Match.Status.FINAL: {"correct_detail"},
            Match.Status.CONDITIONAL: {"schedule_detail", "series_detail"},
            Match.Status.NOT_REQUIRED: {"schedule_detail", "series_detail"},
        }.get(match.status, set())
        if match.outcome in (Match.Outcome.BYE, Match.Outcome.EMPTY):
            valid.discard("correct_detail")
        slots = list(match.slots.all())
        if len(slots) != 2 or not all(
            slot.is_resolved and slot.resolved_entry_id for slot in slots
        ):
            valid -= {"start_detail", "progress_detail", "finalize_detail"}
        return [item for item in actions if item.method.original_function_name in valid]

    def _match_form_view(
        self, request, object_id, *, title, form_class, command, initial=None
    ):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        match = self.get_object(request, object_id)
        if match is None:
            raise Http404
        form = form_class(
            request.POST if request.method == "POST" else None,
            **({"match": match} if issubclass(form_class, ProgressForm) else {}),
            **(
                {"mode": match.effective_series_mode}
                if form_class is SeriesLengthForm
                else {}
            ),
            initial={
                **(initial or {}),
                "expected_revision": match.round.draw.stage.competition.revision,
            },
        )
        if request.method == "POST" and form.is_valid():
            try:
                data = form.cleaned_data.copy()
                command(match, data.pop("expected_revision"), data)
            except (PermissionDenied, ValidationError) as error:
                form.add_error(None, error)
            else:
                self.message_user(request, f"{title} completed.", messages.SUCCESS)
                return HttpResponseRedirect(
                    reverse("admin:competitions_match_change", args=[object_id])
                )
        return _action_response(
            request,
            title=title,
            form=form,
            opts=self.model._meta,
            change_url=reverse("admin:competitions_match_change", args=[object_id]),
            extra={
                **self._match_context(request, match),
                "submit_label": "Save result" if form_class is ResultForm else title,
                "description": (
                    f"Fixed {match.effective_series_length} games: final scores total {match.effective_series_length}; equal scores are a draw."
                    if match.effective_series_mode == "FIXED_GAMES"
                    else f"Best of {match.effective_series_length}: first to {(match.effective_series_length + 1) // 2} game wins advances."
                )
                if issubclass(form_class, ProgressForm)
                else "",
            },
        )

    @action(permissions=["change"], description="Schedule match")
    def schedule_detail(self, request, object_id):
        match = self.get_object(request, object_id)
        return self._match_form_view(
            request,
            object_id,
            title="Schedule match",
            form_class=ScheduleForm,
            initial={"scheduled_at": match.scheduled_at} if match else None,
            command=lambda item, expected_revision, data: schedule_match(
                actor=request.user,
                match_id=item.pk,
                expected_revision=expected_revision,
                **data,
            ),
        )

    @action(permissions=["change"], description="Set series length")
    def series_detail(self, request, object_id):
        match = self.get_object(request, object_id)
        return self._match_form_view(
            request,
            object_id,
            title="Set match series length",
            form_class=SeriesLengthForm,
            initial={"series_length": match.series_length_override} if match else None,
            command=lambda item, expected_revision, data: set_match_series_length(
                actor=request.user,
                match_id=item.pk,
                expected_revision=expected_revision,
                **data,
            ),
        )

    @action(permissions=["change"], description="Start match")
    def start_detail(self, request, object_id):
        return self._match_form_view(
            request,
            object_id,
            title="Start match",
            form_class=RevisionForm,
            command=lambda item, expected_revision, data: start_match(
                actor=request.user,
                match_id=item.pk,
                expected_revision=expected_revision,
            ),
        )

    @action(permissions=["change"], description="Save live score")
    def progress_detail(self, request, object_id):
        match = self.get_object(request, object_id)
        return self._match_form_view(
            request,
            object_id,
            title="Save live score",
            form_class=ProgressForm,
            initial=(
                {
                    "side_one_score": match.side_one_score,
                    "side_two_score": match.side_two_score,
                }
                if match
                else None
            ),
            command=lambda item, expected_revision, data: save_match_progress(
                actor=request.user,
                match_id=item.pk,
                expected_revision=expected_revision,
                **data,
            ),
        )

    @action(permissions=["change"], description="Enter result")
    def finalize_detail(self, request, object_id):
        return self._match_form_view(
            request,
            object_id,
            title="Enter result",
            form_class=ResultForm,
            command=lambda item, expected_revision, data: finalize_match(
                actor=request.user,
                match_id=item.pk,
                expected_revision=expected_revision,
                **data,
            ),
        )

    @action(permissions=["correct"], description="Correct result")
    def correct_detail(self, request, object_id):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        match = self.get_object(request, object_id)
        if match is None:
            raise Http404
        if request.method == "POST" and request.POST.get("token"):
            reason_form = CorrectionReasonForm(request.POST)
            impact = None
            if reason_form.is_valid():
                try:
                    apply_correction(
                        actor=request.user,
                        token=request.POST["token"],
                        internal_reason=reason_form.cleaned_data["internal_reason"],
                    )
                except (PermissionDenied, ValidationError) as error:
                    reason_form.add_error(None, error)
                else:
                    self.message_user(request, "Correction applied.", messages.SUCCESS)
                    return HttpResponseRedirect(
                        reverse("admin:competitions_match_change", args=[object_id])
                    )
            try:
                impact = review_correction_preview(
                    actor=request.user, token=request.POST["token"]
                )
            except (PermissionDenied, ValidationError) as error:
                reason_form.add_error(None, error)
            return _action_response(
                request,
                title="Confirm result correction",
                form=reason_form,
                opts=self.model._meta,
                change_url=reverse("admin:competitions_match_change", args=[object_id]),
                extra={
                    **self._match_context(request, match),
                    "impact": impact,
                    "token": request.POST["token"],
                    "submit_label": "Confirm correction and resets",
                },
            )
        result_form = ResultForm(
            request.POST if request.method == "POST" else None,
            match=match,
            initial={
                "outcome": match.outcome,
                "side_one_score": match.side_one_score,
                "side_two_score": match.side_two_score,
                "winner_position": next(
                    (
                        slot.position
                        for slot in match.slots.all()
                        if slot.resolved_entry_id == match.winner_id
                    ),
                    None,
                ),
                "expected_revision": match.round.draw.stage.competition.revision,
            },
        )
        if request.method == "POST" and result_form.is_valid():
            try:
                data = result_form.cleaned_data.copy()
                impact = preview_correction(
                    actor=request.user,
                    match_id=match.pk,
                    expected_revision=data.pop("expected_revision"),
                    **data,
                )
            except (PermissionDenied, ValidationError) as error:
                result_form.add_error(None, error)
            else:
                return _action_response(
                    request,
                    title="Confirm result correction",
                    form=CorrectionReasonForm(),
                    opts=self.model._meta,
                    change_url=reverse(
                        "admin:competitions_match_change", args=[object_id]
                    ),
                    extra={
                        **self._match_context(request, match),
                        "impact": impact,
                        "token": impact["token"],
                        "submit_label": "Confirm correction and resets",
                    },
                )
        return _action_response(
            request,
            title="Preview result correction",
            form=result_form,
            opts=self.model._meta,
            change_url=reverse("admin:competitions_match_change", args=[object_id]),
            extra={
                **self._match_context(request, match),
                "submit_label": "Preview correction",
            },
        )


@admin.register(ChangeSet)
class ChangeSetAdmin(ReadOnlyCompetitionAdmin):
    list_display = ("competition", "revision", "kind", "actor", "created_at")
    list_filter = ("kind", "competition")
    search_fields = ("kind", "actor__email")

    def has_view_permission(self, request, obj=None):
        return is_organizer_staff(request.user) and request.user.has_perm(
            "competitions.view_changeset"
        )

    def has_change_permission(self, request, obj=None):
        return False


for model in (CompetitionEntrant, MatchSlot):
    admin.site.register(model, ReadOnlyCompetitionAdmin)
