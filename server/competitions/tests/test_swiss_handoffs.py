from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from competitions import commands, swiss_commands
from competitions.handoff_commands import generate_next_stage_draw, validate_draw_source
from competitions.models import Match, StageDraw
from competitions.qualification import stage_qualification
from competitions.tests import test_swiss_commands as command_fixtures
from competitions.tests import test_swiss_plan as plan_fixtures


class SwissHandoffTests(TestCase):
    setUp = plan_fixtures.SwissPlanTests.setUp
    _registration = plan_fixtures.SwissPlanTests._registration
    _competition = plan_fixtures.SwissPlanTests._competition
    _swiss = plan_fixtures.SwissPlanTests._swiss
    _elimination = plan_fixtures.SwissPlanTests._elimination
    _rr = plan_fixtures.SwissPlanTests._rr
    _revision = command_fixtures.SwissCommandTests._revision
    _finish = command_fixtures.SwissCommandTests._finish
    _generate = command_fixtures.SwissCommandTests._generate
    _publish = command_fixtures.SwissCommandTests._publish

    def _save_source(self):
        draw = swiss_commands.save_swiss_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
            ordered_entrant_ids=[e.pk for e in self.entrants],
        )
        self._publish_draw(draw)
        return draw

    def _publish_draw(self, draw):
        commands.publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            stage_id=draw.stage_id,
            expected_revision=self._revision(),
        )
        draw.refresh_from_db()

    def _next(self, destination, **options):
        return generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self._revision(),
            **options,
        )

    def _threshold(self, count, **rules):
        self._competition(count)
        self.stage = self._swiss(
            format="SWISS_THRESHOLD",
            advancement_count=None,
            win_target=rules.get("win_target", 1),
            loss_limit=rules.get("loss_limit", 1),
        )

    def _finish_draw(self, draw):
        for round_ in draw.rounds.filter(state="PUBLISHED").order_by("number"):
            for match in round_.matches.exclude(status="FINAL"):
                commands.finalize_match(
                    actor=self.actor,
                    match_id=match.pk,
                    expected_revision=self._revision(),
                    outcome="PLAYED",
                    side_one_score=match.series_length_override
                    or draw.stage.default_series_length // 2 + 1,
                    side_two_score=0,
                )

    def test_threshold_actual_7_8_9_fields_use_saved_automatic_groups(self):
        for count, sizes in ((13, [4, 3]), (15, [4, 4]), (17, [5, 4])):
            with self.subTest(count=count), transaction.atomic():
                self._threshold(count)
                destination = self._rr(2, [("A", None, 2), ("B", None, 2)])
                source = self._save_source()
                self._finish(source.rounds.get())
                qualified = set(stage_qualification(source)["qualifier_entry_ids"])
                with patch(
                    "competitions.handoff_commands.secrets.SystemRandom"
                ) as random:
                    random.return_value.shuffle.side_effect = lambda rows: (
                        rows.reverse()
                    )
                    saved = self._next(destination)
                self.assertEqual(
                    set(saved.entries.values_list("source_entry_id", flat=True)),
                    qualified,
                )
                self.assertEqual([g.entries.count() for g in saved.groups.all()], sizes)
                self.assertEqual(
                    list(destination.group_plans.values_list("size", flat=True)),
                    [None, None],
                )
                assignment = list(
                    saved.entries.order_by("seed").values_list(
                        "pk", "seed", "group_id", "source_entry_id"
                    )
                )
                revision = self._revision()
                with patch(
                    "competitions.handoff_commands.secrets.SystemRandom",
                    side_effect=AssertionError("reshuffled"),
                ):
                    self.assertEqual(self._next(destination).pk, saved.pk)
                self.assertEqual(self._revision(), revision)
                self.assertEqual(
                    list(
                        saved.entries.order_by("seed").values_list(
                            "pk", "seed", "group_id", "source_entry_id"
                        )
                    ),
                    assignment,
                )
                self._publish_draw(saved)
                validate_draw_source(saved)
                transaction.set_rollback(True)

    def test_unknown_source_resolves_automatic_swiss_limit_and_first_round_audit(self):
        self._threshold(17)
        destination = self._swiss(2, advancement_count=4)
        self._elimination(3)
        source = self._save_source()
        self._finish(source.rounds.get())
        revision = self._revision()
        saved = self._next(destination)
        self.assertEqual(saved.entries.count(), 9)
        self.assertEqual(saved.swiss_round_limit, 4)
        self.assertEqual(self._revision(), revision + 1)
        change = self.competition.changes.get(revision=revision + 1)
        self.assertEqual(change.kind, "successor_draw_saved")
        self.assertEqual(
            change.private_data["swiss_round"],
            swiss_commands._swiss_round_payload(saved.rounds.get()),
        )
        self.assertEqual(change.public_data, {})
        with patch.object(
            swiss_commands,
            "pair_swiss_round",
            side_effect=AssertionError("solver invoked"),
        ):
            self.assertEqual(self._next(destination).pk, saved.pk)
        StageDraw.objects.filter(pk=saved.pk).update(swiss_round_limit=3)
        with self.assertRaises(ValidationError):
            self._publish_draw(saved)
        StageDraw.objects.filter(pk=saved.pk).update(swiss_round_limit=4)
        self._publish_draw(saved)
        self.assertEqual(saved.swiss_round_limit, 4)

    def test_actual_field_rejects_locked_custom_rounds_without_partial_draw(self):
        self._threshold(13)
        destination = self._swiss(2, round_count=8, advancement_count=4)
        self._elimination(3)
        source = self._save_source()
        self._finish(source.rounds.get())
        revision = self._revision()
        with self.assertRaises(ValidationError):
            self._next(destination)
        destination.refresh_from_db()
        self.assertEqual(destination.swiss_round_count, 8)
        self.assertFalse(destination.draws.exists())
        self.assertEqual(self._revision(), revision)

    def test_unknown_field_rejects_incompatible_destinations_and_ineligible_qualifiers(
        self,
    ):
        for destination_kind in ("threshold", "quota", "exact_groups", "eligibility"):
            with self.subTest(destination=destination_kind), transaction.atomic():
                self._threshold(13)
                if destination_kind == "threshold":
                    destination = self._swiss(
                        2,
                        format="SWISS_THRESHOLD",
                        advancement_count=None,
                        win_target=7,
                        loss_limit=2,
                    )
                    self._elimination(3)
                elif destination_kind == "quota":
                    destination = self._swiss(2, advancement_count=8)
                    self._elimination(3)
                elif destination_kind == "exact_groups":
                    destination = self._rr(2, [("A", 4, 2), ("B", 4, 2)])
                else:
                    destination = self._elimination(2)
                source = self._save_source()
                self._finish(source.rounds.get())
                if destination_kind == "eligibility":
                    qualifier = source.entries.get(
                        pk=stage_qualification(source)["qualifier_entry_ids"][0]
                    )
                    qualifier.entrant.registration.status = "PENDING"
                    qualifier.entrant.registration.save(update_fields=("status",))
                revision = self._revision()
                with self.assertRaises(ValidationError):
                    self._next(destination)
                self.assertFalse(destination.draws.exists())
                self.assertEqual(self._revision(), revision)
                transaction.set_rollback(True)

    def test_zero_or_one_threshold_qualifier_blocks_handoff_without_trimming(self):
        for count, expected in ((2, 0), (3, 1)):
            with self.subTest(count=count), transaction.atomic():
                self._threshold(count)
                destination = self._elimination(2)
                source = self._save_source()
                for match in source.rounds.get().matches.exclude(status="FINAL"):
                    commands.finalize_match(
                        actor=self.actor,
                        match_id=match.pk,
                        expected_revision=self._revision(),
                        outcome="DOUBLE_FORFEIT",
                    )
                state = stage_qualification(source)
                self.assertEqual(state["qualification_state"], "RESOLVED")
                self.assertEqual(len(state["qualifier_entry_ids"]), expected)
                self.assertEqual(
                    set(state["qualifier_entry_ids"]),
                    set(
                        source.rounds.get()
                        .matches.filter(outcome="BYE")
                        .values_list("winner_id", flat=True)
                    ),
                )
                with self.assertRaises(ValidationError):
                    self._next(destination)
                self.assertFalse(destination.draws.exists())
                source.stage.refresh_from_db()
                self.assertEqual(source.stage.status, "COMPLETE")
                self.assertIsNone(source.stage.champion_id)
                transaction.set_rollback(True)

    def test_consecutive_swiss_starts_fresh_and_allows_predecessor_meetings(self):
        self._competition(8)
        stages = [self._swiss(i, round_count=2, advancement_count=8) for i in (1, 2, 3)]
        final = self._elimination(4)
        source = self._save_source()
        for index, stage in enumerate(stages):
            self.stage = stage
            if index:
                qualified_ids = set(stage_qualification(source)["qualifier_entry_ids"])
                with patch(
                    "competitions.handoff_commands.secrets.SystemRandom"
                ) as random:
                    random.return_value.shuffle.side_effect = lambda rows: (
                        rows.reverse()
                    )
                    next_draw = self._next(stage)
                self.assertEqual(
                    set(next_draw.entries.values_list("source_entry_id", flat=True)),
                    qualified_ids,
                )
                self.assertTrue(
                    all(
                        (r.wins, r.losses, r.points, r.bye_count, r.status)
                        == (0, 0, 0, 0, "ACTIVE")
                        for r in swiss_commands.swiss_standings(next_draw)
                    )
                )
                self.assertIsNone(next_draw.stage.champion_id)
                previous_pairs = self._entrant_pairs(source.rounds.get(number=1))
                self.assertEqual(
                    self._entrant_pairs(next_draw.rounds.get()), previous_pairs
                )
                self._publish_draw(next_draw)
                source = next_draw
            first = source.rounds.get(number=1)
            self._finish(first)
            second = self._generate()
            self._publish(second)
            self.assertFalse(self._entrant_pairs(first) & self._entrant_pairs(second))
            self._finish(second)
            source.stage.refresh_from_db()
            self.assertEqual(source.stage.status, "COMPLETE")
            self.assertIsNone(source.stage.champion_id)
        saved_final = self._next(final)
        self._publish_draw(saved_final)
        self.assertEqual(saved_final.entries.count(), 8)

    def _entrant_pairs(self, round_):
        return {
            frozenset(m.slots.values_list("entry__entrant_id", flat=True))
            for m in round_.matches.all()
        }

    def test_round_robin_to_swiss_to_double_elimination(self):
        from competitions.round_robin_commands import save_round_robin_draw

        self._competition(4)
        self._rr(1, [("A", 4, 4)])
        self.stage = self._swiss(2, round_count=1, advancement_count=4)
        final = commands.configure_elimination(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
            stage_sequence=3,
            name="Final",
            format="DOUBLE_ELIMINATION",
            grand_final_policy="RESET",
            default_series_length=3,
        )
        source = save_round_robin_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
            group_specs=[("A", 4)],
            ordered_entrant_ids=[e.pk for e in self.entrants],
        )
        self._publish_draw(source)
        self._finish_draw(source)
        swiss_draw = self._next(self.stage)
        self.assertEqual(
            set(swiss_draw.entries.values_list("source_entry_id", flat=True)),
            set(source.entries.values_list("pk", flat=True)),
        )
        self._publish_draw(swiss_draw)
        self._finish(swiss_draw.rounds.get())
        final_draw = self._next(final)
        self._publish_draw(final_draw)
        self.assertEqual(final_draw.entries.count(), 4)

    def test_publication_rejects_group_metadata_outside_the_locked_plan(self):
        self._threshold(13)
        destination = self._rr(2, [("A", None, 2), ("B", None, 2)])
        source = self._save_source()
        self._finish(source.rounds.get())
        saved = self._next(destination)
        saved.groups.filter(number=1).update(name="Changed")
        revision = self._revision()
        with self.assertRaises(ValidationError):
            self._publish_draw(saved)
        saved.refresh_from_db()
        self.assertEqual(saved.state, "DRAFT")
        self.assertEqual(self._revision(), revision)

    def test_unchanged_predecessor_qualifiers_preserve_swiss_rounds_and_refresh_source(
        self,
    ):
        from competitions.round_robin_commands import save_round_robin_draw

        self._competition(4)
        self._rr(1, [("A", 4, 4)])
        self.stage = self._swiss(2, round_count=1, advancement_count=4)
        final = self._elimination(3)
        source = save_round_robin_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
            group_specs=[("A", 4)],
            ordered_entrant_ids=[e.pk for e in self.entrants],
        )
        self._publish_draw(source)
        self._finish_draw(source)
        swiss_draw = self._next(self.stage)
        self._publish_draw(swiss_draw)
        self._finish(swiss_draw.rounds.get())
        final_draw = self._next(final)
        before = swiss_draw.source_fingerprint
        final_before = final_draw.source_fingerprint
        saved = list(
            swiss_draw.entries.order_by("seed").values_list(
                "pk", "seed", "source_entry_id"
            )
        )
        round_payload = swiss_commands._swiss_round_payload(swiss_draw.rounds.get())
        scores = list(
            Match.objects.filter(round__draw=swiss_draw).values_list(
                "pk", "side_one_score", "side_two_score"
            )
        )
        preview = commands.preview_correction(
            actor=self.actor,
            match_id=source.rounds.first().matches.first().pk,
            expected_revision=self._revision(),
            outcome="FORFEIT",
            winner_position=2,
        )
        self.assertEqual(
            preview["handoff_impact"]["retained_draw_ids"],
            [swiss_draw.pk, final_draw.pk],
        )
        commands.apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Correct predecessor outcome",
        )
        swiss_draw.refresh_from_db()
        final_draw.refresh_from_db()
        self.assertNotEqual(swiss_draw.source_fingerprint, before)
        self.assertEqual(final_draw.source_fingerprint, final_before)
        self.assertEqual(
            list(
                swiss_draw.entries.order_by("seed").values_list(
                    "pk", "seed", "source_entry_id"
                )
            ),
            saved,
        )
        self.assertEqual(
            swiss_commands._swiss_round_payload(swiss_draw.rounds.get()), round_payload
        )
        self.assertEqual(
            list(
                Match.objects.filter(round__draw=swiss_draw).values_list(
                    "pk", "side_one_score", "side_two_score"
                )
            ),
            scores,
        )
        swiss_commands.validate_swiss_draw(swiss_draw)
        validate_draw_source(final_draw)

    def test_threshold_unknown_count_becomes_fixed_swiss_quota_for_next_handoff(self):
        from competitions.qualification import (
            preview_qualification_tie,
            confirm_qualification_tie,
        )

        self._threshold(17)
        destination = self._swiss(2, advancement_count=4)
        final = self._elimination(3)
        source = self._save_source()
        self._finish(source.rounds.get())
        saved = self._next(destination)
        self._publish_draw(saved)
        self.stage = destination
        for number in range(1, 5):
            round_ = saved.rounds.get(number=1) if number == 1 else self._generate()
            if number > 1:
                self._publish(round_)
            self._finish(round_)
        state = stage_qualification(saved)
        for tie in state["cutoffs"]:
            preview = preview_qualification_tie(
                actor=self.actor,
                draw_id=saved.pk,
                expected_revision=self._revision(),
                tied_entry_ids=tie["entry_ids"],
                method="MANUAL",
                ordered_entry_ids=tie["entry_ids"],
            )
            confirm_qualification_tie(
                actor=self.actor,
                token=preview["token"],
                internal_reason="Explicit cutoff order",
            )
        state = stage_qualification(saved)
        self.assertEqual(state["qualification_state"], "RESOLVED")
        self.assertEqual(len(state["qualifier_entry_ids"]), 4)
        next_draw = self._next(final)
        self.assertEqual(next_draw.entries.count(), 4)
        self.assertEqual(
            set(next_draw.entries.values_list("source_entry_id", flat=True)),
            set(state["qualifier_entry_ids"]),
        )
        self._publish_draw(next_draw)
