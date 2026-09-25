from django import forms
from pathlib import Path
from django.template.response import TemplateResponse
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import action

from config.organizers import is_organizer_staff

from .admin_forms import PaymentSettingsForm
from .bank_catalogue import BankCatalogueError, sync_bank_catalogue
from .models import (
    Bank,
    PaymentAttempt,
    PaymentIntent,
    PaymentSettings,
    Registration,
    RegistrationMember,
    RegistrationStatusEvent,
)
from .reservations import payment_state
from .services import (
    approve_registration,
    reject_registration,
    start_review,
)


class ImmutableInline:
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RegistrationMemberInline(ImmutableInline, TabularInline):
    model = RegistrationMember
    verbose_name_plural = "Roster (captain marked)"
    readonly_fields = (
        "display_order",
        "is_captain",
        "roster_role",
        "last_name_snapshot",
        "first_name_snapshot",
        "date_of_birth_snapshot",
        "student_id_snapshot",
        "user",
        "gamer_tag_snapshot",
        "school_snapshot",
        "institution",
    )


@admin.display(description="Payment proof")
def payment_proof_preview(obj):
    if not obj.proof_file:
        return "—"
    url = obj.proof_file.url
    if Path(obj.proof_file.name).suffix.lower() not in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }:
        return format_html('<a href="{}">Download proof</a>', url)
    return format_html(
        '<a href="{}" target="_blank" rel="noopener">'
        '<img src="{}" alt="Payment proof" '
        'style="display:block;max-width:100%;max-height:70vh;object-fit:contain"></a>',
        url,
        url,
    )


class PaymentAttemptInline(ImmutableInline, StackedInline):
    model = PaymentAttempt
    show_change_link = True
    readonly_fields = (
        "method",
        "status",
        "amount",
        "currency",
        payment_proof_preview,
        "reference",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "created_at",
    )


class RegistrationStatusEventInline(ImmutableInline, TabularInline):
    model = RegistrationStatusEvent
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")


class GuardedReadOnlyAdmin(ModelAdmin):
    def has_module_permission(self, request):
        return is_organizer_staff(request.user) and super().has_module_permission(
            request
        )

    def has_view_permission(self, request, obj=None):
        return is_organizer_staff(request.user) and super().has_view_permission(
            request, obj
        )

    def has_change_permission(self, request, obj=None):
        return is_organizer_staff(request.user) and super().has_change_permission(
            request, obj
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(Bank)
class BankAdmin(GuardedReadOnlyAdmin):
    list_display = ("short_name", "name", "code", "bin", "is_active", "last_synced_at")
    list_filter = ("is_active",)
    search_fields = ("name", "short_name", "code", "bin", "swift_code")
    change_list_template = "admin/registrations/bank/change_list.html"

    def has_change_permission(self, request, obj=None):
        return False

    def has_sync_permission(self, request):
        return (
            is_organizer_staff(request.user)
            and request.user.has_perm("registrations.change_bank")
            and request.user.has_perm("registrations.view_bank")
        )

    def get_urls(self):
        return [
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_view),
                name="registrations_bank_sync",
            ),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(
            request,
            extra_context={
                **(extra_context or {}),
                "can_sync_banks": self.has_sync_permission(request),
            },
        )

    def sync_view(self, request):
        if not self.has_sync_permission(request):
            raise PermissionDenied
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        try:
            result = sync_bank_catalogue(actor=request.user)
        except BankCatalogueError as error:
            self.message_user(request, str(error), level=messages.ERROR)
        else:
            self.message_user(
                request,
                f"Bank catalogue refreshed: {result['created']} new, "
                f"{result['updated']} refreshed, {result['deactivated']} inactive.",
                level=messages.SUCCESS,
            )
        return HttpResponseRedirect(reverse("admin:registrations_bank_changelist"))


@admin.register(PaymentSettings)
class PaymentSettingsAdmin(ModelAdmin):
    form = PaymentSettingsForm
    fields = (
        "enabled",
        "bank_bin",
        "bank_name",
        "account_number",
        "account_holder",
        "payment_hold_minutes",
    )

    def has_module_permission(self, request):
        return is_organizer_staff(request.user) and super().has_module_permission(
            request
        )

    def has_view_permission(self, request, obj=None):
        return is_organizer_staff(request.user) and super().has_view_permission(
            request, obj
        )

    def has_change_permission(self, request, obj=None):
        return is_organizer_staff(request.user) and super().has_change_permission(
            request, obj
        )

    def has_add_permission(self, request):
        return (
            is_organizer_staff(request.user)
            and super().has_add_permission(request)
            and not PaymentSettings.objects.exists()
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Registration)
class RegistrationAdmin(GuardedReadOnlyAdmin):
    list_display = (
        "id",
        "tournament_game",
        "submitted_by",
        "team_name",
        "team_tag",
        "submitter_role",
        "responsible_name",
        "contact_phone_snapshot",
        "status",
        "submitted_at",
    )
    list_filter = (
        "status",
        "submitter_role",
        "tournament_game__tournament",
        "tournament_game",
        "tournament_game__game",
    )
    search_fields = (
        "team_name",
        "team_tag",
        "payment_intent__reference",
        "payment_intent__transfer_content",
        "submitted_by__email",
        "manager_name_snapshot",
        "contact_phone_snapshot",
        "contact_facebook_snapshot",
        "contact_email_snapshot",
        "contact_discord_snapshot",
        "members__gamer_tag_snapshot",
        "members__first_name_snapshot",
        "members__last_name_snapshot",
        "members__student_id_snapshot",
        "members__school_snapshot",
    )
    list_select_related = ("tournament_game", "submitted_by")
    fieldsets = (
        (
            "Registration",
            {
                "fields": (
                    "tournament_game",
                    "submitted_by",
                    "team_name",
                    "team_tag",
                    "status",
                )
            },
        ),
        (
            "Private contact",
            {
                "fields": (
                    "submitter_role",
                    "manager_name_snapshot",
                    "contact_phone_snapshot",
                    "contact_facebook_snapshot",
                    "contact_email_snapshot",
                    "contact_discord_snapshot",
                )
            },
        ),
        (
            "Payment",
            {
                "fields": (
                    "fee_amount_snapshot",
                    "fee_currency_snapshot",
                    "payment_due_at",
                    "payment_hold_minutes_snapshot",
                )
            },
        ),
        ("Timestamps", {"fields": ("submitted_at", "created_at", "updated_at")}),
    )
    inlines = (
        RegistrationMemberInline,
        PaymentAttemptInline,
        RegistrationStatusEventInline,
    )
    actions = ("mark_under_review", "approve_selected", "reject_selected")
    actions_detail = ("start_review_detail", "approve_detail", "reject_detail")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("members", "payment_attempts")
        )

    @staticmethod
    def _approval_needs_payment(registration):
        return (
            registration.fee_amount_snapshot > 0
            and payment_state(registration) != "VERIFIED"
        )

    def _can_approve(self, request, registration):
        return not self._approval_needs_payment(registration) or request.user.has_perm(
            "registrations.change_paymentattempt"
        )

    def _approval_label(self, registration):
        return (
            "Verify payment and approve"
            if self._approval_needs_payment(registration)
            else "Approve registration"
        )

    @admin.display(description="Responsible person")
    def responsible_name(self, obj):
        if obj.submitter_role == Registration.SubmitterRole.MANAGER:
            return obj.manager_name_snapshot or "—"
        captain = next(
            (member for member in obj.members.all() if member.is_captain), None
        )
        if captain is None:
            return "—"
        return (
            " ".join(
                filter(None, (captain.last_name_snapshot, captain.first_name_snapshot))
            )
            or captain.gamer_tag_snapshot
        )

    def get_list_display(self, request):
        if not self.has_change_permission(request):
            return self.list_display

        @admin.display(description="Review decision")
        def decision_links(obj):
            names = {
                Registration.Status.SUBMITTED: (
                    ("start_review_detail", "Start review"),
                ),
                Registration.Status.UNDER_REVIEW: (
                    ("approve_detail", self._approval_label(obj)),
                    ("reject_detail", "Reject"),
                ),
            }.get(obj.status, ())
            if not self._can_approve(request, obj):
                names = tuple(item for item in names if item[0] != "approve_detail")
            return format_html_join(
                " ",
                '<a class="font-medium text-primary-600 underline" href="{}">{}</a>',
                (
                    (
                        reverse(
                            f"admin:registrations_registration_{name}", args=[obj.pk]
                        ),
                        label,
                    )
                    for name, label in names
                ),
            )

        return (*self.list_display, decision_links)

    def get_actions_detail(self, request, object_id):
        actions = super().get_actions_detail(request, object_id)
        registration = self.get_object(request, object_id)
        if registration is None:
            return []
        valid = {
            Registration.Status.SUBMITTED: {"start_review_detail"},
            Registration.Status.UNDER_REVIEW: {"approve_detail", "reject_detail"},
        }.get(registration.status, set())
        if not self._can_approve(request, registration):
            valid.discard("approve_detail")
        return [item for item in actions if item.method.original_function_name in valid]

    def _decision_view(
        self,
        request,
        object_id,
        title,
        command,
        form_class=forms.Form,
        variant="primary",
    ):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        registration = self.get_object(request, object_id)
        if registration is None:
            raise Http404
        form = form_class(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                command(
                    actor=request.user,
                    registration_id=registration.pk,
                    note=form.cleaned_data.get("reason", ""),
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                self.message_user(
                    request, f"{title} completed.", level=messages.SUCCESS
                )
                return HttpResponseRedirect(
                    reverse("admin:registrations_registration_change", args=[object_id])
                )
        return TemplateResponse(
            request,
            "admin/registrations/registration_decision.html",
            {
                **self.admin_site.each_context(request),
                "title": title,
                "registration": registration,
                "form": form,
                "button_variant": variant,
                "opts": self.model._meta,
                "change_url": reverse(
                    "admin:registrations_registration_change", args=[object_id]
                ),
            },
        )

    @action(permissions=["change"], description="Start review")
    def start_review_detail(self, request, object_id):
        return self._decision_view(request, object_id, "Start review", start_review)

    @action(permissions=["change"], description="Approve registration")
    def approve_detail(self, request, object_id):
        registration = self.get_object(request, object_id)
        if registration is None:
            raise Http404
        if not self._can_approve(request, registration):
            raise PermissionDenied
        return self._decision_view(
            request, object_id, self._approval_label(registration), approve_registration
        )

    @action(permissions=["change"], description="Reject")
    def reject_detail(self, request, object_id):
        return self._decision_view(
            request,
            object_id,
            "Reject",
            reject_registration,
            RejectionReasonForm,
            "danger",
        )

    def _run_transition(self, request, queryset, command, *, label, note=""):
        completed = 0
        for registration in queryset:
            try:
                command(
                    actor=request.user,
                    registration_id=registration.pk,
                    **({"note": note} if note else {}),
                )
            except (PermissionDenied, ValidationError) as error:
                self.message_user(
                    request,
                    f"Registration {registration.pk}: {error}",
                    level=messages.ERROR,
                )
            else:
                completed += 1
        if completed:
            self.message_user(
                request,
                f"{label} {completed} registration(s).",
                level=messages.SUCCESS,
            )

    def _bulk_confirmation(self, request, queryset, *, action_name, title, form):
        return TemplateResponse(
            request,
            "admin/registrations/registration_bulk_decision.html",
            {
                **self.admin_site.each_context(request),
                "title": title,
                "form": form,
                "items": [
                    (
                        registration,
                        self._approval_label(registration)
                        if action_name == "approve_selected"
                        else title,
                    )
                    for registration in queryset
                ],
                "action_name": action_name,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
                "opts": self.model._meta,
            },
        )

    @admin.action(
        permissions=["change"], description="Mark selected registrations under review"
    )
    def mark_under_review(self, request, queryset):
        self._run_transition(
            request, queryset, start_review, label="Started review for"
        )

    @admin.action(permissions=["change"], description="Approve selected registrations")
    def approve_selected(self, request, queryset):
        if request.POST.get("confirm_action") != "1":
            return self._bulk_confirmation(
                request,
                queryset,
                action_name="approve_selected",
                title="Confirm registration approvals",
                form=forms.Form(),
            )
        self._run_transition(request, queryset, approve_registration, label="Approved")

    @admin.action(permissions=["change"], description="Reject selected registrations")
    def reject_selected(self, request, queryset):
        form = RejectionReasonForm(
            request.POST if request.POST.get("confirm_action") == "1" else None
        )
        if not form.is_valid():
            return self._bulk_confirmation(
                request,
                queryset,
                action_name="reject_selected",
                title="Reject registrations",
                form=form,
            )
        self._run_transition(
            request,
            queryset,
            reject_registration,
            label="Rejected",
            note=form.cleaned_data["reason"],
        )


class RejectionReasonForm(forms.Form):
    reason = forms.CharField(
        label="Rejection reason", widget=forms.Textarea, strip=True
    )


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(GuardedReadOnlyAdmin):
    list_display = ("id", "registration", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency", "registration__tournament_game__tournament")
    search_fields = (
        "registration__team_name",
        "registration__team_tag",
        "registration__payment_intent__reference",
        "registration__payment_intent__transfer_content",
        "registration__submitted_by__email",
        "registration__manager_name_snapshot",
        "registration__contact_phone_snapshot",
        "reference",
    )
    list_select_related = ("registration",)
    actions = ()

    def get_readonly_fields(self, request, obj=None):
        return (*super().get_readonly_fields(request, obj), payment_proof_preview)


@admin.register(PaymentIntent)
class PaymentIntentAdmin(GuardedReadOnlyAdmin):
    list_display = (
        "reference",
        "transfer_content",
        "tournament_game",
        "registration",
        "amount",
        "currency",
        "created_at",
    )
    search_fields = (
        "reference",
        "transfer_content",
        "registration__team_name",
        "registration__team_tag",
    )
    list_select_related = ("tournament_game", "registration")
