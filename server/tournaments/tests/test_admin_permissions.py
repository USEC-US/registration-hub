from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase

from accounts.tests.factories import create_account

from tournaments.admin import GameAdmin
from tournaments.models import Game


class TournamentAdminPermissionGateTests(TestCase):
    def test_add_and_delete_permissions_do_not_bypass_organizer_membership(self):
        staff_user = create_account(
            email="catalog-editor@example.com",
            password="strong-password",
            first_name="Catalog",
            last_name="Editor",
            is_staff=True,
        )
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="tournaments", codename="add_game"
            ),
            Permission.objects.get(
                content_type__app_label="tournaments", codename="delete_game"
            ),
        )
        game = Game.objects.create(name="League of Legends", slug="league-of-legends")
        request = RequestFactory().get("/admin/tournaments/game/")
        request.user = staff_user
        model_admin = GameAdmin(Game, AdminSite())

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, game))
