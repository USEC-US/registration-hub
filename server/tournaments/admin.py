from django.contrib import admin
from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import Game, Tournament, TournamentGame


def _is_organizer_staff(user) -> bool:
    return user.is_authenticated and (
        user.is_superuser
        or (user.is_staff and user.groups.filter(name="Organizers").exists())
    )


class OrganizerStaffAdmin(ModelAdmin):
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
        return _is_organizer_staff(request.user) and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return _is_organizer_staff(request.user) and super().has_delete_permission(
            request, obj
        )


@admin.register(Game)
class GameAdmin(OrganizerStaffAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class TournamentGameInline(StackedInline):
    model = TournamentGame
    extra = 1
    min_num = 0
    show_change_link = True
    fields = (
        "game",
        "main_roster_size",
        "substitute_limit",
        "registration_opens_at",
        "registration_closes_at",
        "registration_capacity",
        "fee_amount",
        "fee_currency",
    )


@admin.register(Tournament)
class TournamentAdmin(OrganizerStaffAdmin):
    inlines = [TournamentGameInline]
    list_display = (
        "name",
        "slug",
        "division_count",
        "registration_count",
        "starts_at",
        "ends_at",
        "is_published",
        "is_featured",
        "students_only",
        "cover_image",
    )
    list_filter = ("is_published", "students_only")
    search_fields = ("name", "slug", "location")
    prepopulated_fields = {"slug": ("name",)}
    formfield_overrides = {models.TextField: {"widget": WysiwygWidget}}
    readonly_fields = ("division_count", "registration_count")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _division_count=models.Count("tournament_games", distinct=True),
                _registration_count=models.Count(
                    "tournament_games__registrations", distinct=True
                ),
            )
        )

    @admin.display(description="Divisions", ordering="_division_count")
    def division_count(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            '<a href="{}">{}</a>',
            reverse(
                "admin:tournaments_tournamentgame_changelist",
                query={"tournament__id__exact": obj.pk},
            ),
            obj._division_count,
        )

    @admin.display(
        description="Registrations (all statuses)", ordering="_registration_count"
    )
    def registration_count(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            '<a href="{}">{}</a>',
            reverse(
                "admin:registrations_registration_changelist",
                query={"tournament_game__tournament__id__exact": obj.pk},
            ),
            obj._registration_count,
        )


@admin.register(TournamentGame)
class TournamentGameAdmin(OrganizerStaffAdmin):
    list_display = (
        "tournament",
        "game",
        "registration_count",
        "main_roster_size",
        "substitute_limit",
        "registration_opens_at",
        "registration_closes_at",
        "registration_capacity",
        "fee_amount",
        "fee_currency",
    )
    list_filter = ("tournament", "game", "fee_currency")
    search_fields = (
        "tournament__name",
        "tournament__slug",
        "game__name",
        "game__slug",
    )
    date_hierarchy = "registration_opens_at"
    readonly_fields = ("registration_count",)
    list_select_related = ("tournament", "game")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_registration_count=models.Count("registrations", distinct=True))
        )

    @admin.display(
        description="Registrations (all statuses)", ordering="_registration_count"
    )
    def registration_count(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            '<a href="{}">{}</a>',
            reverse(
                "admin:registrations_registration_changelist",
                query={"tournament_game__id__exact": obj.pk},
            ),
            obj._registration_count,
        )
