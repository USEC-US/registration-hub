from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from unfold.admin import TabularInline, ModelAdmin

from .models import PaymentAttempt, Registration, RegistrationMember, RegistrationStatusEvent
from .services import (
    approve_registration,
    reject_registration,
    review_payment_attempt,
    start_review,
)


class ImmutableInline(TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RegistrationMemberInline(ImmutableInline):
    model = RegistrationMember
    readonly_fields = (
        "user",
        "gamer_tag_snapshot",
        "school_snapshot",
        "is_captain",
        "display_order",
    )


class PaymentAttemptInline(ImmutableInline):
    model = PaymentAttempt
    readonly_fields = (
        "method",
        "status",
        "amount",
        "currency",
        "proof_file",
        "reference",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "created_at",
    )


class RegistrationStatusEventInline(ImmutableInline):
    model = RegistrationStatusEvent
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")


def _is_organizer_staff(user) -> bool:
    return user.is_authenticated and (
        user.is_superuser
        or (user.is_staff and user.groups.filter(name="Organizers").exists())
    )


class GuardedReadOnlyAdmin(ModelAdmin):
    def has_module_permission(self, request):
        return _is_organizer_staff(request.user) and super().has_module_permission(
            request
        )

    def has_view_permission(self, request, obj=None):
        return _is_organizer_staff(request.user) and super().has_view_permission(
            request, obj
        )

    def has_change_permission(self, request, obj=None):
        return _is_organizer_staff(request.user) and super().has_change_permission(
            request, obj
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(Registration)
class RegistrationAdmin(GuardedReadOnlyAdmin):
    list_display = (
        "id",
        "tournament_game",
        "submitted_by",
        "team_name",
        "status",
        "submitted_at",
    )
    list_filter = ("status", "tournament_game__tournament", "tournament_game__game")
    search_fields = ("team_name", "submitted_by__email", "members__gamer_tag_snapshot")
    list_select_related = ("tournament_game", "submitted_by")
    inlines = (RegistrationMemberInline, PaymentAttemptInline, RegistrationStatusEventInline)
    actions = ("mark_under_review", "approve_selected", "reject_selected")

    def _run_transition(self, request, queryset, command):
        completed = 0
        for registration in queryset:
            try:
                command(actor=request.user, registration_id=registration.pk)
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
                f"Applied transition to {completed} registration(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Mark selected registrations under review")
    def mark_under_review(self, request, queryset):
        self._run_transition(request, queryset, start_review)

    @admin.action(description="Approve selected registrations")
    def approve_selected(self, request, queryset):
        self._run_transition(request, queryset, approve_registration)

    @admin.action(description="Reject selected registrations")
    def reject_selected(self, request, queryset):
        self._run_transition(
            request,
            queryset,
            lambda *, actor, registration_id: reject_registration(
                actor=actor,
                registration_id=registration_id,
                note="Rejected by organizer.",
            ),
        )


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(GuardedReadOnlyAdmin):
    list_display = ("id", "registration", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("registration__team_name", "registration__submitted_by__email", "reference")
    list_select_related = ("registration",)
    actions = ("verify_selected", "reject_selected")

    def _review(self, request, queryset, target_status):
        completed = 0
        for payment_attempt in queryset:
            try:
                review_payment_attempt(
                    actor=request.user,
                    payment_attempt_id=payment_attempt.pk,
                    status=target_status,
                )
            except (PermissionDenied, ValidationError) as error:
                self.message_user(
                    request,
                    f"Payment attempt {payment_attempt.pk}: {error}",
                    level=messages.ERROR,
                )
            else:
                completed += 1
        if completed:
            self.message_user(
                request,
                f"Reviewed {completed} payment attempt(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Verify selected payment attempts")
    def verify_selected(self, request, queryset):
        self._review(request, queryset, PaymentAttempt.Status.VERIFIED)

    @admin.action(description="Reject selected payment attempts")
    def reject_selected(self, request, queryset):
        self._review(request, queryset, PaymentAttempt.Status.REJECTED)
