from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from competitions.models import Competition, Match, MatchSlot, Round, Stage, StageDraw
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

    def test_double_elimination_requires_a_policy_and_other_formats_forbid_it(self):
        self.assertEqual(self.stage.grand_final_policy, "")
        for sequence, format_, policy in (
            (2, Stage.Format.DOUBLE_ELIMINATION, ""),
            (3, Stage.Format.DOUBLE_ELIMINATION, "UNKNOWN"),
            (4, Stage.Format.SINGLE_ELIMINATION, "RESET"),
        ):
            with self.subTest(format=format_, policy=policy):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Stage.objects.create(
                        competition=self.competition,
                        sequence=sequence,
                        name=f"Stage {sequence}",
                        format=format_,
                        grand_final_policy=policy,
                        series_mode=Stage.SeriesMode.BEST_OF,
                        default_series_length=3,
                    )

        for sequence, policy in ((5, "RESET"), (6, "NO_RESET")):
            stage = Stage.objects.create(
                competition=self.competition,
                sequence=sequence,
                name=f"Stage {sequence}",
                format=Stage.Format.DOUBLE_ELIMINATION,
                grand_final_policy=policy,
                series_mode=Stage.SeriesMode.BEST_OF,
                default_series_length=3,
            )
            self.assertEqual(stage.grand_final_policy, policy)

    def test_match_source_requires_an_outcome_and_empty_slot_forbids_one(self):
        draw = StageDraw.objects.create(stage=self.stage, version=1)
        round_ = Round.objects.create(draw=draw, number=1)
        source = round_.matches.create(number=1, code="SOURCE")

        for number, outcome in ((2, ""), (3, "UNKNOWN")):
            target = round_.matches.create(number=number, code=f"TARGET-{number}")
            with self.subTest(source_outcome=outcome):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    MatchSlot.objects.create(
                        match=target,
                        position=1,
                        source_match=source,
                        source_outcome=outcome,
                    )

        for number, outcome in ((4, MatchSlot.SourceOutcome.WINNER), (5, "LOSER")):
            target = round_.matches.create(number=number, code=f"TARGET-{number}")
            with self.subTest(empty_source_outcome=outcome):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    MatchSlot.objects.create(
                        match=target,
                        position=1,
                        is_empty=True,
                        source_outcome=outcome,
                    )

        target = round_.matches.create(number=6, code="VALID-TARGET")
        for position, outcome in (
            (1, MatchSlot.SourceOutcome.WINNER),
            (2, "LOSER"),
        ):
            slot = MatchSlot.objects.create(
                match=target,
                position=position,
                source_match=source,
                source_outcome=outcome,
            )
            self.assertEqual(slot.source_outcome, outcome)

    def test_double_elimination_sections_and_reserved_match_statuses_exist(self):
        self.assertEqual(Round.Section.UPPER, "UPPER")
        self.assertEqual(Round.Section.LOWER, "LOWER")
        self.assertEqual(Round.Section.FINALS, "FINALS")
        self.assertEqual(Round.Section.NORMAL, "NORMAL")
        self.assertEqual(Match.Status.CONDITIONAL, "CONDITIONAL")
        self.assertEqual(Match.Status.NOT_REQUIRED, "NOT_REQUIRED")
