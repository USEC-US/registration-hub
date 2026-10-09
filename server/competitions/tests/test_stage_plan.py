from itertools import product

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from competitions.commands import (
    configure_elimination,
    create_competition,
    publish_draw,
    save_elimination_draw,
    select_entrants,
)
from competitions.models import Match, Stage
from competitions.round_robin_commands import (
    configure_round_robin,
    save_round_robin_draw,
)
from competitions.tests.test_commands import CompetitionCommandTests


class StagePlanTests(TestCase):
    setUp = CompetitionCommandTests.setUp
    _registration = CompetitionCommandTests._registration

    def _configure(self, sizes, quotas):
        from competitions.stage_commands import set_stage_groups

        self.competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        source = configure_round_robin(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            name="Groups1",
            meetings=1,
            series_mode="BEST_OF",
            default_series_length=1,
            win_points=3,
            draw_points=1,
            loss_points=0,
        )
        self.competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[self._registration(i + 10).pk for i in range(sum(sizes))],
        )
        self.competition.refresh_from_db()
        set_stage_groups(
            actor=self.actor,
            stage_id=source.pk,
            expected_revision=self.competition.revision,
            group_specs=[
                (f"Group {i}", size, quota)
                for i, (size, quota) in enumerate(zip(sizes, quotas), 1)
            ],
        )
        self.competition.refresh_from_db()
        destination = configure_elimination(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            name="Playoffs",
            default_series_length=1,
            format="SINGLE_ELIMINATION",
            stage_sequence=2,
        )
        self.competition.refresh_from_db()
        return source, destination, entrants

    def test_arbitrary_partitions_and_unequal_quotas(self):
        from competitions.stage_commands import validate_stage_plan

        for sizes, quotas, incoming, outgoing in (
            ((3, 3, 2), (2, 2, 2), 8, 6),
            ((3, 2, 2), (2, 2, 2), 7, 6),
            ((2, 5, 3), (1, 4, 2), 10, 7),
        ):
            with self.subTest(sizes=sizes), transaction.atomic():
                self._configure(sizes, quotas)
                rows = validate_stage_plan(self.competition)
                self.assertEqual(
                    [r["incoming_count"] for r in rows], [incoming, outgoing]
                )
                self.assertEqual([r["outgoing_count"] for r in rows], [outgoing, None])
                transaction.set_rollback(True)

    def test_small_partitions_use_same_equations(self):
        from competitions.stage_commands import set_stage_groups, validate_stage_plan

        source, _, _ = self._configure((2, 3), (1, 2))
        for quotas in product(range(1, 3), range(1, 4)):
            self.competition.refresh_from_db()
            set_stage_groups(
                actor=self.actor,
                stage_id=source.pk,
                expected_revision=self.competition.revision,
                group_specs=[("A", 2, quotas[0]), ("B", 3, quotas[1])],
            )
            self.assertEqual(
                validate_stage_plan(self.competition)[1]["incoming_count"], sum(quotas)
            )

    def test_whole_plan_rejects_incompatible_future_groups_without_publication(self):
        from competitions.stage_commands import set_stage_groups

        source, destination, entrants = self._configure((3, 3, 2), (2, 2, 2))
        configure_round_robin(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_sequence=2,
            name="Later",
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
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
            group_specs=[("A", 3, 2), ("B", 3, 2), ("C", 2, 2)],
        )
        self.competition.refresh_from_db()
        ids = [e.pk for e in entrants]
        save_round_robin_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            group_specs=[("Group 1", 2), ("Group 2", 2), ("Group 3", 2)],
            ordered_entrant_ids=ids,
            memberships=[ids[:3], ids[3:6], ids[6:]],
        )
        self.competition.refresh_from_db()
        revision = self.competition.revision
        with self.assertRaises(ValidationError):
            publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=revision,
            )
        source.refresh_from_db()
        self.competition.refresh_from_db()
        self.assertIsNone(source.published_at)
        self.assertEqual(self.competition.revision, revision)

    def test_plan_locks_and_draw_labels_are_contiguous(self):
        from competitions.stage_commands import set_stage_groups

        source, _, entrants = self._configure((3, 2, 2), (2, 2, 2))
        ids = [e.pk for e in entrants]
        draw = save_round_robin_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            group_specs=[("Group 1", 2), ("Group 2", 2), ("Group 3", 2)],
            ordered_entrant_ids=ids,
            memberships=[ids[:3], ids[3:5], ids[5:]],
        )
        self.assertEqual(
            list(
                Match.objects.filter(round__draw=draw)
                .order_by("pk")
                .values_list("code", flat=True)
            ),
            ["Groups1-M1", "Groups1-M2", "Groups1-M3", "Groups1-M4", "Groups1-M5"],
        )
        self.competition.refresh_from_db()
        publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        with self.assertRaises(ValidationError):
            configure_elimination(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
                name="New",
                default_series_length=1,
                format="SINGLE_ELIMINATION",
                stage_sequence=3,
            )
        with self.assertRaises(ValidationError):
            set_stage_groups(
                actor=self.actor,
                stage_id=source.pk,
                expected_revision=self.competition.revision,
                group_specs=[("A", 7, 6)],
            )
        self.assertEqual(Stage.objects.count(), 2)

    def test_elimination_labels_and_replacement_restart(self):
        self.competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        for format_, policy in (
            ("SINGLE_ELIMINATION", ""),
            ("DOUBLE_ELIMINATION", "RESET"),
        ):
            self.competition.refresh_from_db()
            configure_elimination(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
                name="Playoffs",
                format=format_,
                grand_final_policy=policy,
                default_series_length=1,
            )
            self.competition.refresh_from_db()
            entrants = select_entrants(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
                registration_ids=[r.pk for r in self.registrations],
            )
            for _ in range(2):
                self.competition.refresh_from_db()
                draw = save_elimination_draw(
                    actor=self.actor,
                    competition_id=self.competition.pk,
                    expected_revision=self.competition.revision,
                    entrant_order=[e.pk for e in entrants],
                )
                codes = list(
                    Match.objects.filter(round__draw=draw)
                    .order_by("pk")
                    .values_list("code", flat=True)
                )
                self.assertEqual(
                    codes, [f"Playoffs-M{i}" for i in range(1, len(codes) + 1)]
                )

    def test_scope_quota_order_and_removal_validation(self):
        from competitions.stage_commands import (
            set_stage_advancement,
            reorder_stages,
            remove_stage,
        )

        source, destination, _ = self._configure((2, 3), (1, 2))
        for value in (True, 2.0, "2", 0, 257):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                set_stage_advancement(
                    actor=self.actor,
                    stage_id=destination.pk,
                    expected_revision=self.competition.revision,
                    advancement_count=value,
                )
        with self.assertRaises(ValidationError):
            save_elimination_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                stage_id=999999,
                expected_revision=self.competition.revision,
                randomize=True,
            )
        reorder_stages(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_ids=[destination.pk, source.pk],
        )
        self.assertEqual(
            list(self.competition.stages.values_list("pk", flat=True)),
            [destination.pk, source.pk],
        )
        self.competition.refresh_from_db()
        remove_stage(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        source.refresh_from_db()
        self.assertEqual(source.sequence, 1)
