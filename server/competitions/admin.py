from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import TabularInline
from unfold.decorators import action

from config.organizers import is_organizer_staff, require_organizer
from tournaments.admin import OrganizerStaffAdmin

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
    return TemplateResponse(
        request,
        "admin/competitions/action_form.html",
        {
            **admin.site.each_context(request),
            "title": title,
            "form": form,
            "opts": opts,
            "change_url": change_url,
            **(extra or {}),
        },
    )


@admin.register(Competition)
class CompetitionAdmin(OrganizerStaffAdmin):
    list_display = ("tournament_game", "revision", "stage_status", "updated_at")
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
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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
                    reverse("admin:competitions_round_change", args=[object_id])
                )
        return _action_response(
            request,
            title="Set round series length",
            form=form,
            opts=self.model._meta,
            change_url=reverse("admin:competitions_round_change", args=[object_id]),
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
        return super().get_queryset(request).select_related(
            "round__draw__stage", "winner__entrant"
        )

    def get_actions_detail(self, request, object_id):
        actions = super().get_actions_detail(request, object_id)
        match = self.get_object(request, object_id)
        if match is None:
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
        return [
            item for item in actions if item.method.original_function_name in valid
        ]

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

    @action(permissions=["change"], description="Finalize result")
    def finalize_detail(self, request, object_id):
        return self._match_form_view(
            request,
            object_id,
            title="Finalize result",
            form_class=ResultForm,
            command=lambda item, expected_revision, data: finalize_match(
                actor=request.user,
                match_id=item.pk,
                expected_revision=expected_revision,
                **data,
            ),
        )

    @action(permissions=["change"], description="Correct final result")
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
                extra={"impact": impact, "token": request.POST["token"]},
            )
        result_form = ResultForm(
            request.POST if request.method == "POST" else None,
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
                    extra={"impact": impact, "token": impact["token"]},
                )
        return _action_response(
            request,
            title="Preview result correction",
            form=result_form,
            opts=self.model._meta,
            change_url=reverse("admin:competitions_match_change", args=[object_id]),
        )


@admin.register(ChangeSet)
class ChangeSetAdmin(ReadOnlyCompetitionAdmin):
    list_display = ("competition", "revision", "kind", "actor", "created_at")
    list_filter = ("kind", "competition")
    search_fields = ("kind", "actor__email")


for model in (CompetitionEntrant, MatchSlot):
    admin.site.register(model, ReadOnlyCompetitionAdmin)
