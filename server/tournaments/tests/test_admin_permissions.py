from datetime import timedelta
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.tests.factories import create_account

from tournaments.admin import GameAdmin, TournamentAdmin, TournamentGameAdmin
from tournaments.models import Game, Tournament, TournamentGame


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

    def test_tournament_and_division_permissions_require_organizer_membership(self):
        staff_user = create_account(
            email="tournament-editor@example.com",
            password="strong-password",
            first_name="Tournament",
            last_name="Editor",
            is_staff=True,
        )
        staff_user.user_permissions.add(
            *[
                Permission.objects.get(
                    content_type__app_label="tournaments",
                    codename=codename,
                )
                for codename in (
                    "view_tournament",
                    "change_tournament",
                    "add_tournamentgame",
                    "change_tournamentgame",
                    "delete_tournamentgame",
                )
            ]
        )
        game = Game.objects.create(name="Valorant", slug="valorant")
        tournament = Tournament.objects.create(name="USEC Summer", slug="usec-summer")
        tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=7),
            fee_amount=Decimal("0.00"),
            fee_currency="VND",
        )
        request = RequestFactory().get("/admin/tournaments/tournament/")
        request.user = staff_user
        site = AdminSite()
        tournament_admin = TournamentAdmin(Tournament, site)
        tournament_game_admin = TournamentGameAdmin(TournamentGame, site)

        self.assertFalse(tournament_admin.has_view_permission(request, tournament))
        self.assertFalse(tournament_admin.has_change_permission(request, tournament))
        self.assertFalse(tournament_game_admin.has_add_permission(request))
        self.assertFalse(
            tournament_game_admin.has_change_permission(request, tournament_game)
        )
        self.assertFalse(
            tournament_game_admin.has_delete_permission(request, tournament_game)
        )
