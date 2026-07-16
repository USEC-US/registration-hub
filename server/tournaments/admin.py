from django.contrib import admin

from .models import Game, Tournament, TournamentGame


def _is_organizer_staff(user) -> bool:
    return user.is_authenticated and (
        user.is_superuser
        or (user.is_staff and user.groups.filter(name="Organizers").exists())
    )


class OrganizerStaffAdmin(admin.ModelAdmin):
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


@admin.register(Game)
class GameAdmin(OrganizerStaffAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tournament)
class TournamentAdmin(OrganizerStaffAdmin):
    list_display = ("name", "slug", "starts_at", "ends_at", "is_published")
    list_filter = ("is_published",)
    search_fields = ("name", "slug", "location")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TournamentGame)
class TournamentGameAdmin(OrganizerStaffAdmin):
    list_display = (
        "tournament",
        "game",
        "team_size_min",
        "team_size_max",
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
