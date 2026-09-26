from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
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
    match_card,
    result_summary,
    workspace_url,
)

from .commands import (
    apply_correction,
    configure_single_elimination,
    create_competition,
    finalize_match,
    preview_correction,
    publish_draw,
    review_correction_preview,
    save_match_progress,
    save_single_elimination_draw,
    schedule_match,
    select_entrants,
    set_match_series_length,
    set_round_series_length,
    start_match,
)
from .forms import (
    CompetitionSetupForm,
    CorrectionReasonForm,
    DrawForm,
    EntrantSelectionForm,
    NewCompetitionForm,
    ProgressForm,
    RevisionForm,
    ResultForm,
    ScheduleForm,
    SeriesLengthForm,
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
)


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
        stage = competition.stages.select_related("champion").first()
        draw = (
            stage.draws.exclude(state=StageDraw.State.SUPERSEDED).first()
            if stage
            else None
        )
        entrants = list(competition.entrants.order_by("pk"))
        published = bool(stage and stage.published_at)
        can_manage = self.has_change_permission(request, competition)
        can_view_matches = admin.site.get_model_admin(Match).has_view_permission(
            request
        )
        can_operate = can_view_matches and request.user.has_perm(
            "competitions.change_match"
        )
        can_view_changes = request.user.has_perm("competitions.view_changeset")
        url = workspace_url(competition.pk)
        selected_tab = request.GET.get("tab", "bracket" if draw else "setup")
        if selected_tab not in ("setup", "entrants", "bracket", "changes"):
            raise Http404
        if selected_tab == "changes" and not can_view_changes:
            raise PermissionDenied
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
                    "url": reverse(
                        f"admin:competitions_competition_{action_name}",
                        args=[competition.pk],
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
            }
            for item in entrants
        ]
        rounds = []
        all_cards = []
        if draw:
            entries = [
                {
                    "seed": item.seed,
                    "name": item.entrant.display_name,
                    "status": item.entrant.get_status_display(),
                }
                for item in draw.entries.select_related("entrant").order_by("seed")
            ]
        if draw and can_view_matches:
            slots = MatchSlot.objects.select_related(
                "entry__entrant", "resolved_entry__entrant", "source_match"
            )
            matches = Match.objects.select_related(
                "round__draw__stage"
            ).prefetch_related(Prefetch("slots", queryset=slots))
            draw_rounds = list(
                draw.rounds.prefetch_related(Prefetch("matches", queryset=matches))
            )
            for index, round_ in enumerate(draw_rounds):
                cards = [
                    match_card(match, request.user) for match in round_.matches.all()
                ]
                all_cards.extend(cards)
                remaining = len(draw_rounds) - index
                label = {1: "Final", 2: "Semifinals", 3: "Quarterfinals"}.get(
                    remaining, f"Round {round_.number}"
                )
                rounds.append(
                    {
                        "label": label,
                        "series_length": round_.series_length_override
                        or stage.default_series_length,
                        "series_url": reverse(
                            "admin:competitions_round_series_detail", args=[round_.pk]
                        )
                        if can_operate
                        and published
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
                    "url": reverse(
                        "admin:competitions_match_change",
                        args=[change.private_data["match_id"]],
                    )
                    if change.private_data.get("match_id") and can_view_matches
                    else None,
                }
                for change in changes_page
            ]
        return TemplateResponse(
            request,
            "admin/competitions/workspace.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "original": competition,
                "title": f"{competition.tournament_game.tournament.name} · {competition.tournament_game.game.name}",
                "competition": competition,
                "stage": stage,
                "draw": draw,
                "workspace_url": url,
                "bracket_url": workspace_url(competition.pk, "bracket"),
                "setup_url": workspace_url(competition.pk, "setup"),
                "tab": selected_tab,
                "tabs": [
                    {
                        "label": label,
                        "url": workspace_url(competition.pk, tab),
                        "active": tab == selected_tab,
                    }
                    for tab, label in [
                        ("bracket", "Bracket & matches"),
                        ("entrants", "Entrants"),
                        ("setup", "Setup"),
                        ("changes", "Changes"),
                    ]
                    if tab != "changes" or can_view_changes
                ],
                "can_manage": can_manage,
                "can_view_matches": can_view_matches,
                "primary_action": primary_action,
                "setup_steps": setup_steps,
                "entrants_url": setup_steps[1]["url"],
                "entries": entries,
                "rounds": rounds,
                "participant_count": len(entrants),
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

    def get_urls(self):
        return [
            path(
                "create/<int:division_id>/",
                self.admin_site.admin_view(self.create_view),
                name="competitions_competition_create_for_division",
            )
        ] + super().get_urls()

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
        self, request, object_id, *, title, form_class, command, form_kwargs=None
    ):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        competition = self.get_object(request, object_id)
        if competition is None:
            raise Http404
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
        if request.method == "POST" and form.is_valid():
            try:
                data = form.cleaned_data.copy()
                command(competition, data.pop("expected_revision"), data)
            except (PermissionDenied, ValidationError) as error:
                form.add_error(None, error)
            else:
                self.message_user(request, f"{title} completed.", messages.SUCCESS)
                return HttpResponseRedirect(
                    reverse("admin:competitions_competition_change", args=[object_id])
                )
        return _action_response(
            request,
            title=title,
            form=form,
            opts=self.model._meta,
            change_url=reverse(
                "admin:competitions_competition_change", args=[object_id]
            ),
            extra={
                "workspace_url": workspace_url(competition.pk),
                "description": f"{competition.tournament_game.tournament.name} · {competition.tournament_game.game.name}",
                "submit_label": {
                    "Configure single elimination": "Save setup",
                    "Select approved entrants": "Save entrants",
                    "Save bracket draw": "Save and preview bracket",
                    "Publish saved draw": "Publish bracket",
                }.get(title, title),
            },
        )

    @action(permissions=["change"], description="Configure single elimination")
    def configure_detail(self, request, object_id):
        competition = self.get_object(request, object_id)
        stage = competition.stages.order_by("sequence").first() if competition else None
        initial = (
            {"name": stage.name, "default_series_length": stage.default_series_length}
            if stage
            else None
        )
        return self._competition_form_view(
            request,
            object_id,
            title="Configure single elimination",
            form_class=CompetitionSetupForm,
            form_kwargs={"initial": initial},
            command=lambda item, expected_revision, data: configure_single_elimination(
                actor=request.user,
                competition_id=item.pk,
                expected_revision=expected_revision,
                **data,
            ),
        )

    @action(permissions=["change"], description="Select approved entrants")
    def entrants_detail(self, request, object_id):
        competition = self.get_object(request, object_id)
        if competition is None:
            raise Http404
        initial = {
            "registrations": competition.entrants.values_list(
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
        return self._competition_form_view(
            request,
            object_id,
            title="Save bracket draw",
            form_class=DrawForm,
            form_kwargs={"competition": competition},
            command=lambda item, expected_revision, data: save_single_elimination_draw(
                actor=request.user,
                competition_id=item.pk,
                expected_revision=expected_revision,
                entrant_order=data.get("entrant_order"),
                randomize=data["randomize"],
            ),
        )

    @action(permissions=["change"], description="Publish saved draw")
    def publish_detail(self, request, object_id):
        return self._competition_form_view(
            request,
            object_id,
            title="Publish saved draw",
            form_class=RevisionForm,
            command=lambda item, expected_revision, data: publish_draw(
                actor=request.user,
                competition_id=item.pk,
                expected_revision=expected_revision,
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
                    workspace_url(round_.draw.stage.competition_id, "bracket")
                )
        return _action_response(
            request,
            title="Set round series length",
            form=form,
            opts=self.model._meta,
            change_url=workspace_url(round_.draw.stage.competition_id, "bracket"),
            extra={
                "workspace_url": workspace_url(round_.draw.stage.competition_id),
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
        actions = self.get_actions_detail(request, str(match.pk))
        card = match_card(match, request.user)
        return {
            "workspace_url": workspace_url(
                match.round.draw.stage.competition_id, "bracket"
            ),
            "bracket_url": workspace_url(
                match.round.draw.stage.competition_id, "bracket"
            ),
            "setup_url": workspace_url(match.round.draw.stage.competition_id, "setup"),
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
                    match.round.draw.stage.competition_id, "changes"
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
        if match.round.draw.state != StageDraw.State.PUBLISHED:
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
        }[match.status]
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
                "description": f"Best of {match.effective_series_length}: first to {(match.effective_series_length + 1) // 2} game wins advances."
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
