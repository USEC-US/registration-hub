from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from competitions.commands import (
    configure_elimination,
    create_competition,
    select_entrants,
)
from competitions.models import Stage, StageDraw
from competitions.round_robin_commands import (
    configure_round_robin,
    save_round_robin_draw,
)
from competitions.stage_commands import (
    remove_stage,
    reorder_stages,
    set_stage_advancement,
    set_stage_groups,
    validate_stage_plan,
)
from competitions.tests.test_commands import CompetitionCommandTests


class SwissPlanTests(TestCase):
    setUp = CompetitionCommandTests.setUp
    _registration = CompetitionCommandTests._registration

    def _competition(self, count=8):
        self.competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        self.entrants = select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[self._registration(i + 10).pk for i in range(count)],
        )
        self.competition.refresh_from_db()

    def _swiss(self, sequence=1, **overrides):
        from competitions.swiss_commands import configure_swiss

        self.competition.refresh_from_db()
        values = dict(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_sequence=sequence,
            name=f"Swiss {sequence}",
            format="SWISS_FIXED",
            series_mode="BEST_OF",
            default_series_length=3,
            round_count=None,
            win_target=None,
            loss_limit=None,
            advancement_count=4,
            win_points=Decimal(3),
            draw_points=Decimal(1),
            loss_points=Decimal(0),
            tiebreaks=["OPPONENT_POINTS", "GAME_DIFFERENCE", "GAMES_WON"],
        )
        values.update(overrides)
        return configure_swiss(**values)

    def _elimination(self, sequence, quota=None):
        self.competition.refresh_from_db()
        stage = configure_elimination(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_sequence=sequence,
            name=f"Final {sequence}",
            format="SINGLE_ELIMINATION",
            default_series_length=3,
        )
        if quota is not None:
            self.competition.refresh_from_db()
            set_stage_advancement(
                actor=self.actor,
                stage_id=stage.pk,
                expected_revision=self.competition.revision,
                advancement_count=quota,
            )
        return stage

    def _rr(self, sequence, groups):
        self.competition.refresh_from_db()
        stage = configure_round_robin(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_sequence=sequence,
            name=f"Groups {sequence}",
            meetings=1,
            series_mode="BEST_OF",
            default_series_length=1,
            win_points=3,
            draw_points=1,
            loss_points=0,
        )
        self.competition.refresh_from_db()
        set_stage_groups(
            actor=self.actor,
            stage_id=stage.pk,
            expected_revision=self.competition.revision,
            group_specs=groups,
        )
        return stage

    def test_private_incomplete_swiss_is_configurable_but_not_valid(self):
        self._competition()
        stage = self._swiss()
        self.assertIsNone(stage.swiss_round_count)
        with self.assertRaises(ValidationError):
            validate_stage_plan(self.competition)
        self._elimination(2)
        self.assertEqual(
            [r["incoming_count"] for r in validate_stage_plan(self.competition)], [8, 4]
        )

    def test_consecutive_and_intermediate_presets(self):
        self._competition(16)
        self._elimination(1, 12)
        for sequence in (2, 3, 4):
            self._swiss(sequence, advancement_count=8)
        self._elimination(5)
        rows = validate_stage_plan(self.competition)
        self.assertEqual([r["incoming_count"] for r in rows], [16, 12, 8, 8, 8])
        self.assertEqual(
            [r["requires_actual_field_validation"] for r in rows], [False] * 5
        )
        self.assertEqual(
            [r["stage_id"] for r in rows],
            list(self.competition.stages.values_list("pk", flat=True)),
        )

    def test_unknown_counts_restore_and_become_unknown_again(self):
        self._competition(16)
        self._swiss(
            format="SWISS_THRESHOLD", win_target=3, loss_limit=3, advancement_count=None
        )
        self._rr(2, [("A", None, 2), ("B", None, 2)])
        self._swiss(3, advancement_count=4)
        self._swiss(
            4,
            format="SWISS_THRESHOLD",
            win_target=2,
            loss_limit=2,
            advancement_count=None,
        )
        self._elimination(5, 4)
        self._swiss(6, advancement_count=2)
        self._elimination(7)
        rows = validate_stage_plan(self.competition)
        self.assertEqual(
            [r["incoming_count"] for r in rows], [16, None, 4, 4, None, 4, 2]
        )
        self.assertEqual(
            [r["outgoing_count"] for r in rows], [None, 4, 4, None, 4, 2, None]
        )
        self.assertEqual(
            [r["requires_actual_field_validation"] for r in rows],
            [False, True, False, False, True, False, False],
        )
        self.assertIsNone(rows[1]["ordinary_match_count"])
        self.assertIsNone(rows[4]["ordinary_match_count"])

    def test_unknown_fixed_quota_restores_known_field(self):
        self._competition()
        self._swiss(
            format="SWISS_THRESHOLD", win_target=2, loss_limit=2, advancement_count=None
        )
        self._swiss(2, round_count=64, advancement_count=8)
        self._elimination(3)
        rows = validate_stage_plan(self.competition)
        self.assertIsNone(rows[1]["incoming_count"])
        self.assertIsNone(rows[1]["ordinary_match_count"])
        self.assertTrue(rows[1]["requires_actual_field_validation"])
        self.assertEqual(rows[2]["incoming_count"], 8)

    def test_invalid_swiss_rules_do_not_persist_or_increment_revision(self):
        self._competition()
        for bad in (
            {"round_count": True},
            {"round_count": 0},
            {"round_count": 65},
            {"round_count": 8},
            {"win_target": 1},
            {"advancement_count": None},
            {"advancement_count": 1},
            {"advancement_count": 9},
            {"advancement_count": True},
            {"tiebreaks": ["HEAD_TO_HEAD"]},
            {"tiebreaks": ["MATCH_WINS", "MATCH_WINS"]},
            {"win_points": 1},
            {"loss_points": -1},
            {"draw_points": Decimal("1.001")},
            {"default_series_length": 2},
            {
                "format": "SWISS_THRESHOLD",
                "win_target": 2,
                "loss_limit": 2,
                "advancement_count": None,
                "series_mode": "FIXED_GAMES",
            },
            {
                "format": "SWISS_THRESHOLD",
                "win_target": True,
                "loss_limit": 2,
                "advancement_count": None,
            },
            {
                "format": "SWISS_THRESHOLD",
                "win_target": 4,
                "loss_limit": 5,
                "advancement_count": None,
            },
            {"format": "SWISS_THRESHOLD", "win_target": 2, "loss_limit": 2},
            {"name": ""},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self._swiss(**bad)
            self.competition.refresh_from_db()
            self.assertEqual(self.competition.revision, 2)
            self.assertFalse(self.competition.stages.exists())

    def test_unknown_fields_still_validate_absolute_limits(self):
        self._competition()
        self._swiss(
            format="SWISS_THRESHOLD", win_target=2, loss_limit=2, advancement_count=None
        )
        for bad in (
            {"round_count": 65},
            {"advancement_count": 257},
            {
                "format": "SWISS_THRESHOLD",
                "win_target": 33,
                "loss_limit": 33,
                "advancement_count": None,
            },
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self._swiss(2, **bad)

    def test_saved_custom_and_automatic_round_policy_survives_entrant_changes(self):
        self._competition()
        stage = self._swiss(round_count=5)
        self.competition.refresh_from_db()
        select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[e.registration_id for e in self.entrants[:4]],
        )
        stage.refresh_from_db()
        self.assertEqual(stage.swiss_round_count, 5)
        self._elimination(2)
        with self.assertRaises(ValidationError):
            validate_stage_plan(self.competition)
        stage = self._swiss(advancement_count=2)
        self.assertIsNone(stage.swiss_round_count)
        self.assertEqual(
            validate_stage_plan(self.competition)[0]["ordinary_match_count"], 4
        )

    def test_reorder_and_remove_cannot_leave_swiss_final(self):
        self._competition()
        swiss = self._swiss()
        final = self._elimination(2)
        self.competition.refresh_from_db()
        revision = self.competition.revision
        with self.assertRaises(ValidationError):
            reorder_stages(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=revision,
                stage_ids=[final.pk, swiss.pk],
            )
        with self.assertRaises(ValidationError):
            remove_stage(
                actor=self.actor, stage_id=final.pk, expected_revision=revision
            )
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.revision, revision)
        self.assertEqual(
            list(self.competition.stages.values_list("pk", flat=True)),
            [swiss.pk, final.pk],
        )

    def test_entire_plan_locked_after_first_publication(self):
        self._competition()
        first = self._elimination(1, 4)
        swiss = self._swiss(2)
        self._elimination(3)
        Stage.objects.filter(pk=first.pk).update(published_at=timezone.now())
        self.competition.refresh_from_db()
        revision = self.competition.revision
        with self.assertRaises(ValidationError):
            self._swiss(2, round_count=2)
        swiss.refresh_from_db()
        self.competition.refresh_from_db()
        self.assertIsNone(swiss.swiss_round_count)
        self.assertEqual(self.competition.revision, revision)

    def test_format_changes_clear_swiss_fields_and_retire_downstream_drafts(self):
        self._competition()
        swiss = self._swiss(round_count=3)
        final = self._elimination(2)
        draft = StageDraw.objects.create(stage=final, version=1)
        self._rr(1, [("A", 8, 4)])
        swiss.refresh_from_db()
        draft.refresh_from_db()
        self.assertIsNone(swiss.swiss_round_count)
        self.assertEqual(draft.state, "SUPERSEDED")
        self._swiss(
            format="SWISS_THRESHOLD", win_target=2, loss_limit=2, advancement_count=None
        )
        self._elimination(1, 4)
        swiss.refresh_from_db()
        self.assertIsNone(swiss.swiss_win_target)
        self.assertIsNone(swiss.swiss_loss_limit)

    def test_oversized_round_robin_estimate_rejected(self):
        self._competition(256)
        self._rr(1, [("A", 256, 2)])
        self._elimination(2)
        with self.assertRaises(ValidationError):
            validate_stage_plan(self.competition)

    def test_fixed_games_and_optional_match_wins_are_supported(self):
        self._competition()
        stage = self._swiss(
            series_mode="FIXED_GAMES", default_series_length=2, tiebreaks=["MATCH_WINS"]
        )
        self._elimination(2)
        self.assertEqual(stage.series_mode, "FIXED_GAMES")
        self.assertEqual(
            validate_stage_plan(self.competition)[0]["ordinary_match_count"], 12
        )

    def test_automatic_groups_remain_automatic_after_draw_and_entrant_edit(self):
        self._competition(7)
        stage = self._rr(1, [("A", None, 2), ("B", None, 2)])
        self._elimination(2)
        self.competition.refresh_from_db()
        draw = save_round_robin_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            group_specs=[("A", 2), ("B", 2)],
            ordered_entrant_ids=[e.pk for e in self.entrants],
        )
        self.assertEqual([g.entries.count() for g in draw.groups.all()], [4, 3])
        self.assertEqual(
            list(stage.group_plans.values_list("size", flat=True)), [None, None]
        )
        self.competition.refresh_from_db()
        select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[e.registration_id for e in self.entrants[:6]],
        )
        self.assertEqual(
            list(stage.group_plans.values_list("size", flat=True)), [None, None]
        )
        self.assertEqual(
            validate_stage_plan(self.competition)[0]["ordinary_match_count"], 6
        )

    def test_actual_unknown_field_validates_before_retiring_or_saving_draw(self):
        from competitions.command_support import _persist_stage_draw

        self._competition()
        self._swiss(
            format="SWISS_THRESHOLD", win_target=2, loss_limit=2, advancement_count=None
        )
        stage = self._swiss(2, round_count=64)
        self._elimination(3)
        draft = StageDraw.objects.create(stage=stage, version=1)
        with self.assertRaisesMessage(ValidationError, "Swiss rounds"):
            _persist_stage_draw(stage, [e.pk for e in self.entrants], randomized=False)
        draft.refresh_from_db()
        self.assertEqual(draft.state, "DRAFT")
        self.assertEqual(stage.draws.count(), 1)

    def test_three_swiss_stages_then_elimination(self):
        self._competition(16)
        for sequence, quota in ((1, 8), (2, 6), (3, 4)):
            self._swiss(sequence, advancement_count=quota)
        self._elimination(4)
        self.assertEqual(
            [r["incoming_count"] for r in validate_stage_plan(self.competition)],
            [16, 8, 6, 4],
        )


class GroupSizeTests(TestCase):
    def test_locked_automatic_group_sizes(self):
        from competitions.stage_commands import resolve_group_sizes

        groups = [("A", None, 2), ("B", None, 2)]
        for count, expected in ((7, [4, 3]), (8, [4, 4]), (9, [5, 4])):
            self.assertEqual(resolve_group_sizes(groups, count), expected)
        self.assertEqual(
            resolve_group_sizes([("A", None, 4), ("B", None, 1)], 7), [4, 3]
        )
        with self.assertRaises(ValidationError):
            resolve_group_sizes(groups, 3)
        self.assertEqual(groups, [("A", None, 2), ("B", None, 2)])

    def test_bad_exact_mixed_and_quota_groups(self):
        from competitions.stage_commands import resolve_group_sizes

        for groups, count in (
            ([("A", 4, 2)], 7),
            ([("A", None, 2), ("B", 3, 2)], 7),
            ([("A", None, 257)], 7),
            ([("A", None, True)], 7),
            ([("A", True, 1)], 7),
            ([("A", 2, 3)], 2),
            ([], 7),
            ([("A", None, 1)], True),
        ):
            with (
                self.subTest(groups=groups, count=count),
                self.assertRaises(ValidationError),
            ):
                resolve_group_sizes(groups, count)
