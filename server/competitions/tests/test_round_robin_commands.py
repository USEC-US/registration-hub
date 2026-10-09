from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from competitions.commands import (
    create_competition,
    finalize_match,
    publish_draw,
    save_match_progress,
    select_entrants,
    set_match_series_length,
    set_round_series_length,
)
from competitions.models import Match, Stage, StageDraw
from competitions.round_robin_commands import (
    configure_round_robin,
    save_round_robin_draw,
)
from competitions.tests import test_commands


class RoundRobinCommandTests(TestCase):
    setUp = test_commands.CompetitionCommandTests.setUp
    _registration = test_commands.CompetitionCommandTests._registration

    def configure(self, **overrides):
        self.competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        return self.setup_stage(**overrides)

    def setup_stage(self, **overrides):
        self.competition.refresh_from_db()
        return configure_round_robin(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            **{
                "name": "Groups",
                "meetings": 1,
                "series_mode": "FIXED_GAMES",
                "default_series_length": 2,
                "win_points": Decimal("3"),
                "draw_points": Decimal("1"),
                "loss_points": Decimal("0"),
                "tiebreaks": ("HEAD_TO_HEAD", "GAME_DIFFERENCE", "GAMES_WON"),
                **overrides,
            },
        )

    def choose(self, size=8):
        for index in range(len(self.registrations) + 1, size + 1):
            self.registrations.append(self._registration(index))
        self.competition.refresh_from_db()
        self.entrants = select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[row.pk for row in self.registrations[:size]],
        )
        return [row.pk for row in self.entrants]

    def draw(self, **overrides):
        self.competition.refresh_from_db()
        return save_round_robin_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            **{
                "group_specs": [("A", 1), ("B", 2)],
                "ordered_entrant_ids": [row.pk for row in self.entrants],
                **overrides,
            },
        )

    def publish(self):
        self.competition.refresh_from_db()
        return publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )

    def test_manual_unequal_groups_and_double_meetings(self):
        self.configure(meetings=2)
        ids = self.choose()
        draw = self.draw(memberships=[ids[:3], ids[3:]])
        self.assertEqual([group.entries.count() for group in draw.groups.all()], [3, 5])
        self.assertEqual(Match.objects.filter(round__draw=draw).count(), 26)
        self.assertFalse(Match.objects.filter(round__draw=draw, outcome="BYE").exists())
        self.assertEqual(self.publish().state, StageDraw.State.PUBLISHED)

    def test_random_draw_is_saved_and_preview_does_not_reshuffle(self):
        self.configure()
        self.choose()
        draw = self.draw(randomize=True)
        seeds = list(draw.entries.values_list("entrant_id", flat=True))
        draw.refresh_from_db()
        self.assertEqual(list(draw.entries.values_list("entrant_id", flat=True)), seeds)
        self.assertTrue(draw.randomized)
        self.assertEqual([group.entries.count() for group in draw.groups.all()], [4, 4])

    def test_invalid_membership_and_qualifying_places_do_not_write(self):
        self.configure()
        ids = self.choose()
        for memberships, specs in (
            ([ids[:1], ids[1:]], [("A", 1), ("B", 2)]),
            ([ids[:4], ids[3:7]], [("A", 1), ("B", 2)]),
            ([ids[:4], ids[4:]], [("A", 5), ("B", 2)]),
        ):
            with (
                self.subTest(memberships=memberships),
                self.assertRaises(ValidationError),
            ):
                self.draw(memberships=memberships, group_specs=specs)
        self.assertFalse(self.competition.stages.first().draws.exists())

    def test_setup_change_supersedes_draft_and_publication_locks_rules(self):
        self.configure()
        self.choose()
        draw = self.draw()
        self.setup_stage(meetings=2)
        draw.refresh_from_db()
        self.assertEqual(draw.state, StageDraw.State.SUPERSEDED)
        with self.assertRaises(ValidationError):
            self.publish()
        self.draw()
        self.publish()
        with self.assertRaises(ValidationError):
            self.setup_stage(tiebreaks=())

    def test_reselecting_before_publication_preserves_old_draw_identity(self):
        self.configure()
        self.choose()
        old = self.draw()
        entry_ids = list(old.entries.values_list("pk", flat=True))
        self.choose(size=6)
        old.refresh_from_db()
        self.assertEqual(old.state, StageDraw.State.SUPERSEDED)
        self.assertEqual(list(old.entries.values_list("pk", flat=True)), entry_ids)
        self.assertEqual(self.draw().entries.count(), 6)

    def test_invalid_points_and_criteria(self):
        self.configure()
        for overrides in (
            {"win_points": Decimal("1")},
            {"draw_points": Decimal("1.001")},
            {"win_points": Decimal("Infinity")},
            {"loss_points": Decimal("-1")},
            {"tiebreaks": ("UNKNOWN",)},
            {"tiebreaks": ("MATCH_WINS", "MATCH_WINS")},
            {"meetings": 3},
            {"series_mode": "BEST_OF", "default_series_length": 2},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.setup_stage(**overrides)

    def test_publication_revalidates_saved_group_fixtures(self):
        self.configure()
        self.choose()
        draw = self.draw()
        match = Match.objects.filter(round__draw=draw).first()
        match.slots.filter(position=1).update(resolved_entry_id=draw.entries.last().pk)
        with self.assertRaises(ValidationError):
            self.publish()

    def published_group(self, **rules):
        self.configure(**rules)
        self.choose(size=3)
        draw = self.draw(group_specs=[("A", 1)])
        self.publish()
        return draw

    def result(self, match, **overrides):
        self.competition.refresh_from_db()
        return finalize_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            **{
                "outcome": "PLAYED",
                "side_one_score": 1,
                "side_two_score": 1,
                **overrides,
            },
        )

    def test_fixed_games_progress_and_draw(self):
        from competitions.round_robin_commands import group_standings

        draw = self.published_group()
        match = Match.objects.filter(round__draw=draw).first()
        self.competition.refresh_from_db()
        save_match_progress(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            side_one_score=1,
            side_two_score=0,
        )
        self.assertEqual(
            [row.points for row in group_standings(draw.groups.get())["standings"]],
            [0, 0, 0],
        )
        self.competition.refresh_from_db()
        with self.assertRaises(ValidationError):
            save_match_progress(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self.competition.revision,
                side_one_score=1,
                side_two_score=1,
            )
        for scores in ((0, 0), (2, 1), (1.5, 0.5), (True, 1), (-1, 3)):
            with self.subTest(scores=scores), self.assertRaises(ValidationError):
                self.result(match, side_one_score=scores[0], side_two_score=scores[1])
        final = self.result(match)
        self.assertIsNone(final.winner)
        self.assertEqual(final.applied_series_mode, "FIXED_GAMES")
        self.assertEqual(
            sorted(
                row.points for row in group_standings(draw.groups.get())["standings"]
            ),
            [0, 1, 1],
        )

    def test_last_numbered_match_does_not_complete_earlier_pending_play(self):
        draw = self.published_group()
        self.result(Match.objects.filter(round__draw=draw).last())
        draw.stage.refresh_from_db()
        self.assertEqual(draw.stage.status, Stage.Status.IN_PROGRESS)
        self.assertIsNone(draw.stage.champion)

    def test_cutoff_tie_awaits_resolution(self):
        draw = self.published_group(tiebreaks=())
        for match in Match.objects.filter(round__draw=draw):
            self.result(match)
        draw.stage.refresh_from_db()
        self.assertEqual(draw.stage.status, Stage.Status.AWAITING)

    def test_tie_inside_all_qualifying_places_completes_without_fake_champion(self):
        self.configure(tiebreaks=())
        self.choose(size=3)
        draw = self.draw(group_specs=[("A", 3)])
        self.publish()
        for match in Match.objects.filter(round__draw=draw):
            self.result(match)
        draw.stage.refresh_from_db()
        self.assertEqual(draw.stage.status, Stage.Status.COMPLETE)
        self.assertIsNone(draw.stage.champion)
        self.assertFalse(draw.stage.completed_without_champion)

    def test_even_fixed_length_override_and_started_mode_lock(self):
        draw = self.published_group()
        match = Match.objects.filter(round__draw=draw).first()
        self.competition.refresh_from_db()
        set_match_series_length(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            series_length=4,
        )
        self.result(match, side_one_score=2, side_two_score=2)
        self.competition.refresh_from_db()
        with self.assertRaises(ValidationError):
            set_match_series_length(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self.competition.revision,
                series_length=2,
            )
        other = Match.objects.filter(round__draw=draw, started_at__isnull=True).first()
        set_round_series_length(
            actor=self.actor,
            round_id=other.round_id,
            expected_revision=self.competition.revision,
            series_length=4,
        )
        match.refresh_from_db()
        self.assertEqual(
            (match.applied_series_mode, match.effective_series_length),
            ("FIXED_GAMES", 4),
        )
