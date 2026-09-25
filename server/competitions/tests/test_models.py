from datetime import timedelta

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from competitions.models import Competition, Round, Stage, StageDraw
from tournaments.models import Game, Tournament, TournamentGame


class CompetitionModelTests(TestCase):
    def setUp(self):
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(name="Cup", slug="cup")
        self.division = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        self.competition = Competition.objects.create(tournament_game=self.division)
        self.stage = Stage.objects.create(
            competition=self.competition,
            sequence=1,
            name="Final bracket",
            format=Stage.Format.SINGLE_ELIMINATION,
            series_mode=Stage.SeriesMode.BEST_OF,
            default_series_length=3,
        )

    def test_competition_protects_owning_division(self):
        with self.assertRaises(ProtectedError):
            self.division.delete()

    def test_match_length_precedence_is_stage_then_round_then_match(self):
        draw = StageDraw.objects.create(stage=self.stage, version=1)
        round_ = Round.objects.create(draw=draw, number=1)
        match = round_.matches.create(number=1, code="M-1")

        self.assertEqual(match.effective_series_length, 3)
        round_.series_length_override = 5
        round_.save(update_fields=("series_length_override",))
        self.assertEqual(match.effective_series_length, 5)
        match.series_length_override = 7
        self.assertEqual(match.effective_series_length, 7)
