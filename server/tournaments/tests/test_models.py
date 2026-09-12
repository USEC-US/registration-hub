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
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=7),
            fee_amount="50000.00",
            fee_currency="VND",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            TournamentGame.objects.create(
                tournament=self.tournament,
                game=self.game,
                main_roster_size=5,
                substitute_limit=0,
                registration_opens_at=timezone.now(),
                registration_closes_at=timezone.now() + timedelta(days=7),
                fee_amount="50000.00",
                fee_currency="VND",
            )

    def test_exact_five_player_game_is_a_team_game(self):
        tournament_game = TournamentGame.objects.create(
            tournament=self.tournament,
            game=self.game,
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=7),
            fee_amount="0.00",
            fee_currency="VND",
        )

        self.assertTrue(tournament_game.is_team)
        self.assertFalse(tournament_game.is_individual)

    def test_roster_configuration_constraints_and_solo_classification(self):
        for main, substitutes in ((0, 0), (2, -1)):
            with self.subTest(main=main, substitutes=substitutes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    TournamentGame.objects.create(
                        tournament=self.tournament,
                        game=self.game,
                        main_roster_size=main,
                        substitute_limit=substitutes,
                        registration_opens_at=timezone.now(),
                        registration_closes_at=timezone.now() + timedelta(days=1),
                        fee_amount=0,
                    )
        division = TournamentGame(main_roster_size=1, substitute_limit=0)
        self.assertTrue(division.is_individual)
        self.assertFalse(division.is_team)
