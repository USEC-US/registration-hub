from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.tests.factories import create_account

from registrations.models import Registration
from tournaments.models import Game, Tournament, TournamentGame


@override_settings(ROOT_URLCONF="config.urls")
class PublicTournamentApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name="Valorant", slug="valorant")
        self.published = Tournament.objects.create(
            name="USEC Summer 2026",
            slug="usec-summer-2026",
            description="Summer tournament",
            location="HCMUS",
            is_published=True,
        )
        self.unpublished = Tournament.objects.create(
            name="Draft Event",
            slug="draft-event",
            is_published=False,
        )
        self.tournament_game = TournamentGame.objects.create(
            tournament=self.published,
            game=self.game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now() - timedelta(hours=1),
            registration_closes_at=timezone.now() + timedelta(days=2),
            registration_capacity=1,
            fee_amount=Decimal("50000.00"),
            fee_currency="VND",
        )

    def test_list_returns_only_published_tournaments(self):
        response = self.client.get("/api/tournaments/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item["slug"] for item in response.data}
        self.assertEqual(slugs, {"usec-summer-2026"})

    def test_detail_returns_published_tournament_games(self):
        response = self.client.get("/api/tournaments/usec-summer-2026/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], "usec-summer-2026")
        self.assertEqual(response.data["tournament_games"][0]["game_name"], "Valorant")
        self.assertEqual(response.data["tournament_games"][0]["team_size_min"], 5)
        self.assertEqual(response.data["tournament_games"][0]["fee_currency"], "VND")
        self.assertEqual(
            response.data["tournament_games"][0]["registration_state"], "open"
        )
        self.assertTrue(
            response.data["tournament_games"][0]["is_registration_open"]
        )

    def test_unpublished_detail_returns_404(self):
        response = self.client.get("/api/tournaments/draft-event/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_uses_one_availability_time_at_closing_boundary(self):
        closing_boundary = timezone.now()
        self.tournament_game.registration_closes_at = closing_boundary
        self.tournament_game.save(update_fields=("registration_closes_at",))

        with patch(
            "tournaments.serializers.timezone.now",
            side_effect=(
                closing_boundary - timedelta(microseconds=1),
                closing_boundary,
            ),
        ) as mocked_now:
            response = self.client.get("/api/tournaments/usec-summer-2026/")

        game_data = response.data["tournament_games"][0]
        self.assertEqual(mocked_now.call_count, 1)
        self.assertEqual(game_data["registration_state"], "open")
        self.assertTrue(game_data["is_registration_open"])

    def test_detail_query_count_does_not_grow_with_tournament_games(self):
        second_game = Game.objects.create(name="League of Legends", slug="lol")
        TournamentGame.objects.create(
            tournament=self.published,
            game=second_game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now() - timedelta(hours=1),
            registration_closes_at=timezone.now() + timedelta(days=2),
            registration_capacity=1,
            fee_amount=Decimal("50000.00"),
            fee_currency="VND",
        )

        with self.assertNumQueries(2):
            response = self.client.get("/api/tournaments/usec-summer-2026/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["tournament_games"]), 2)

    def test_full_game_reports_full_state(self):
        user = create_account(
            email="player@example.com",
            password="strong-password",
            first_name="Player",
            last_name="User",
        )
        Registration.objects.create(
            tournament_game=self.tournament_game,
            submitted_by=user,
            team_name="Full Team",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=Decimal("50000.00"),
            fee_currency_snapshot="VND",
        )

        response = self.client.get("/api/tournaments/usec-summer-2026/")

        self.assertEqual(
            response.data["tournament_games"][0]["registration_state"],
            "full",
        )
        self.assertFalse(
            response.data["tournament_games"][0]["is_registration_open"]
        )
