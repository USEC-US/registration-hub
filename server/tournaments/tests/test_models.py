from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from tournaments.models import Game, Tournament, TournamentGame


class TournamentGameModelTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(name="Valorant", slug="valorant")
        self.tournament = Tournament.objects.create(
            name="USEC Summer 2026", slug="usec-summer-2026"
        )

    def test_tournament_has_one_configuration_per_game(self):
        TournamentGame.objects.create(
            tournament=self.tournament,
            game=self.game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=7),
            fee_amount="50000.00",
            fee_currency="VND",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            TournamentGame.objects.create(
                tournament=self.tournament,
                game=self.game,
                team_size_min=5,
                team_size_max=5,
                registration_opens_at=timezone.now(),
                registration_closes_at=timezone.now() + timedelta(days=7),
                fee_amount="50000.00",
                fee_currency="VND",
            )

    def test_exact_five_player_game_is_a_team_game(self):
        tournament_game = TournamentGame.objects.create(
            tournament=self.tournament,
            game=self.game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=7),
            fee_amount="0.00",
            fee_currency="VND",
        )

        self.assertTrue(tournament_game.is_team)
        self.assertFalse(tournament_game.is_individual)
