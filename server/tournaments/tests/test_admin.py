from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase

from accounts.tests.factories import create_account

from tournaments.admin import GameAdmin
from tournaments.models import Game


class TournamentAdminAccessTests(TestCase):
    def test_direct_catalog_permissions_do_not_bypass_organizer_membership(self):
        staff_user = create_account(
            email="catalog-staff@example.com",
            password="strong-password",
            first_name="Catalog",
            last_name="Staff",
            is_staff=True,
        )
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="tournaments", codename="view_game"
            ),
            Permission.objects.get(
                content_type__app_label="tournaments", codename="change_game"
            ),
        )
        game = Game.objects.create(name="Chess", slug="chess")
        request = RequestFactory().get("/admin/tournaments/game/")
        request.user = staff_user
        model_admin = GameAdmin(Game, AdminSite())

        self.assertFalse(model_admin.has_module_permission(request))
        self.assertFalse(model_admin.has_view_permission(request, game))
        self.assertFalse(model_admin.has_change_permission(request, game))
