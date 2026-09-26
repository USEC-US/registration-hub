from collections import Counter

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.db import transaction
from django.utils import timezone

from competitions import commands
from competitions.models import Match, MatchSlot, Stage, StageDraw
from competitions.tests import test_commands


class DoubleEliminationCommandTests(TestCase):
    setUp = test_commands.CompetitionCommandTests.setUp
    _registration = test_commands.CompetitionCommandTests._registration

    def configure(self, competition, policy="RESET", format="DOUBLE_ELIMINATION"):
        self.assertTrue(
            callable(getattr(commands, "configure_elimination", None)),
            "Shared elimination setup command is required",
        )
        competition.refresh_from_db()
        return commands.configure_elimination(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            name="Bracket",
            default_series_length=3,
            format=format,
            grand_final_policy=policy,
        )

    def draw(self, count=4, policy="RESET", publish=True):
        competition = commands.create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        self.configure(competition, policy)
        registrations = self.registrations[:count]
        registrations += [self._registration(i) for i in range(4, count + 1)]
        competition.refresh_from_db()
        entrants = commands.select_entrants(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            registration_ids=[item.pk for item in registrations],
        )
        competition.refresh_from_db()
        draw = commands.save_elimination_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            entrant_order=[item.pk for item in entrants],
        )
        if publish:
            self.publish(competition)
        return competition, draw

    def publish(self, competition):
        competition.refresh_from_db()
        return commands.publish_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
        )

    def finish(self, competition, match, position=1, outcome="PLAYED"):
        competition.refresh_from_db()
        scores = (
            {
                "side_one_score": 2 if position == 1 else 0,
                "side_two_score": 2 if position == 2 else 0,
            }
            if outcome == "PLAYED"
            else {"winner_position": position}
        )
        return commands.finalize_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            outcome=outcome,
            **scores,
        )

    def match(self, draw, section, number=1, match_number=1):
        return Match.objects.get(
            round__draw=draw,
            round__section=section,
            round__number=number,
            number=match_number,
        )

    def test_complete_fields_preserve_two_lives_and_both_final_policies(self):
        # Each subcase rolls back independently while retaining the base fixture.
        for count in (2, 4, 5, 8):
            for policy in ("RESET", "NO_RESET"):
                for final_position in (1, 2):
                    with self.subTest(
                        count=count, policy=policy, winner=final_position
                    ):
                        with transaction.atomic():
                            competition, draw = self.draw(count, policy)
                            losses = Counter()
                            played = 0
                            while True:
                                ready = [
                                    m
                                    for m in Match.objects.filter(
                                        round__draw=draw, status=Match.Status.PENDING
                                    ).select_related("round")
                                    if all(
                                        s.is_resolved and s.resolved_entry_id
                                        for s in m.slots.all()
                                    )
                                ]
                                if not ready:
                                    break
                                match = ready[0]
                                entries = list(
                                    match.slots.order_by("position").values_list(
                                        "resolved_entry_id", flat=True
                                    )
                                )
                                self.assertTrue(all(losses[e] < 2 for e in entries))
                                position = (
                                    final_position
                                    if match.round.section == "FINALS"
                                    else 1
                                )
                                self.finish(competition, match, position)
                                losses[entries[2 - position]] += 1
                                played += 1
                                self.assertLessEqual(played, 2 * count - 1)
                            stage = Stage.objects.get(pk=draw.stage_id)
                            self.assertEqual(stage.status, Stage.Status.COMPLETE)
                            champion = draw.entries.get(entrant_id=stage.champion_id).pk
                            for entry in draw.entries.all():
                                if entry.pk != champion:
                                    expected = (
                                        1
                                        if (
                                            policy == "NO_RESET"
                                            and final_position == 2
                                            and losses[entry.pk] == 1
                                        )
                                        else 2
                                    )
                                    self.assertEqual(losses[entry.pk], expected)
                            self.assertEqual(
                                played,
                                2 * count
                                - 2
                                + (policy == "RESET" and final_position == 2),
                            )
                            for match in Match.objects.filter(
                                round__draw=draw, outcome__in=("BYE", "EMPTY")
                            ):
                                self.assertIsNone(match.side_one_score)
                                self.assertIsNone(match.side_two_score)
                            transaction.set_rollback(True)

    def test_upper_loss_fills_loser_route_and_unresolved_sources_wait(self):
        competition, draw = self.draw()
        upper = self.match(draw, "UPPER")
        loser = upper.slots.get(position=2).resolved_entry_id
        self.finish(competition, upper, outcome="FORFEIT")
        lower = self.match(draw, "LOWER")
        self.assertEqual(lower.slots.get(position=1).resolved_entry_id, loser)
        self.assertFalse(lower.slots.get(position=2).is_resolved)
        self.assertEqual(lower.status, Match.Status.PENDING)
        self.assertEqual(
            upper.dependent_slots.filter(source_outcome="LOSER").count(), 1
        )

    def test_inactive_reset_can_be_scheduled_but_cannot_be_played(self):
        competition, draw = self.draw(2)
        reset = self.match(draw, "FINALS", 2)
        self.assertEqual(reset.status, Match.Status.CONDITIONAL)
        for status in ("CONDITIONAL", "NOT_REQUIRED"):
            Match.objects.filter(pk=reset.pk).update(status=status)
            for command, kwargs in (
                (commands.start_match, {}),
                (
                    commands.save_match_progress,
                    {"side_one_score": 0, "side_two_score": 0},
                ),
                (commands.finalize_match, {"outcome": "FORFEIT", "winner_position": 1}),
            ):
                competition.refresh_from_db()
                with self.assertRaises(ValidationError):
                    command(
                        actor=self.actor,
                        match_id=reset.pk,
                        expected_revision=competition.revision,
                        **kwargs,
                    )
        Match.objects.filter(pk=reset.pk).update(status="CONDITIONAL")
        competition.refresh_from_db()
        commands.schedule_match(
            actor=self.actor,
            match_id=reset.pk,
            expected_revision=competition.revision,
            scheduled_at=timezone.now(),
        )
        competition.refresh_from_db()
        commands.set_match_series_length(
            actor=self.actor,
            match_id=reset.pk,
            expected_revision=competition.revision,
            series_length=5,
        )
        self.finish(competition, self.match(draw, "UPPER"))
        self.finish(competition, self.match(draw, "FINALS"), 2, "FORFEIT")
        reset.refresh_from_db()
        self.assertEqual(reset.status, Match.Status.PENDING)
        self.assertEqual(reset.effective_series_length, 5)
        self.assertIsNotNone(reset.scheduled_at)

    def test_double_forfeits_empty_both_routes_and_complete_without_champion(self):
        competition, draw = self.draw(4)
        for match in list(
            Match.objects.filter(
                round__draw=draw, round__section="UPPER", round__number=1
            )
        ):
            self.finish(competition, match, outcome="DOUBLE_FORFEIT")
            self.assertFalse(
                match.dependent_slots.filter(resolved_entry__isnull=False).exists()
            )
        stage = Stage.objects.get(pk=draw.stage_id)
        self.assertEqual(stage.status, Stage.Status.COMPLETE)
        self.assertTrue(stage.completed_without_champion)
        self.assertIsNone(stage.champion_id)
        self.assertEqual(
            self.match(draw, "FINALS", 2).status, Match.Status.NOT_REQUIRED
        )

    def test_lower_double_forfeit_leaves_upper_final_winner_and_does_not_reset(self):
        competition, draw = self.draw(4)
        self.finish(competition, self.match(draw, "UPPER", match_number=1))
        self.finish(competition, self.match(draw, "UPPER", match_number=2))
        lower = self.match(draw, "LOWER")
        self.finish(competition, lower, outcome="DOUBLE_FORFEIT")
        self.assertFalse(
            lower.dependent_slots.filter(resolved_entry__isnull=False).exists()
        )
        self.finish(competition, self.match(draw, "UPPER", 2))
        self.finish(competition, self.match(draw, "FINALS"))
        self.assertEqual(
            self.match(draw, "FINALS", 2).status, Match.Status.NOT_REQUIRED
        )
        self.assertEqual(
            Stage.objects.get(pk=draw.stage_id).status, Stage.Status.COMPLETE
        )

    def test_policy_validation_and_format_switch_require_fresh_draw(self):
        competition, draw = self.draw(publish=False)
        for policy, format in (
            ("", "DOUBLE_ELIMINATION"),
            ("BAD", "DOUBLE_ELIMINATION"),
            ("RESET", "SINGLE_ELIMINATION"),
            ("", "ROUND_ROBIN"),
        ):
            with self.assertRaises(ValidationError):
                self.configure(competition, policy, format)
        self.configure(competition, "NO_RESET")
        draw.refresh_from_db()
        self.assertEqual(draw.state, StageDraw.State.SUPERSEDED)
        with self.assertRaises(ValidationError):
            self.publish(competition)
        self.configure(competition, "", "SINGLE_ELIMINATION")
        competition.refresh_from_db()
        fresh = commands.save_elimination_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            entrant_order=list(competition.entrants.values_list("pk", flat=True)),
        )
        self.assertEqual(fresh.version, 2)
        self.assertTrue(
            all(
                "-NORMAL-" not in m.code
                for m in Match.objects.filter(round__draw=fresh)
            )
        )
        self.publish(competition)
        with self.assertRaises(ValidationError):
            self.configure(competition)

    def test_publication_rejects_wrong_routing_cycle_and_policy(self):
        competition, draw = self.draw(publish=False)
        lower = self.match(draw, "LOWER")
        slot = lower.slots.get(position=1)
        original = slot.source_match_id
        for source in (lower.pk, self.match(draw, "UPPER", match_number=2).pk):
            slot.source_match_id = source
            slot.save(update_fields=("source_match",))
            with self.assertRaises(ValidationError):
                self.publish(competition)
        slot.source_match_id = original
        slot.save(update_fields=("source_match",))
        Stage.objects.filter(pk=draw.stage_id).update(grand_final_policy="NO_RESET")
        with self.assertRaises(ValidationError):
            self.publish(competition)

    def test_stale_and_repeated_results_do_not_advance_twice(self):
        competition, draw = self.draw(2)
        match = self.match(draw, "UPPER")
        competition.refresh_from_db()
        stale = competition.revision
        self.finish(competition, match)
        with self.assertRaises(ValidationError):
            commands.finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=stale,
                outcome="FORFEIT",
                winner_position=1,
            )
        with self.assertRaises(ValidationError):
            self.finish(competition, match)

    def test_not_required_final_rejects_scores_even_with_both_entrants_resolved(self):
        competition, draw = self.draw(2)
        self.finish(competition, self.match(draw, "UPPER"))
        self.finish(competition, self.match(draw, "FINALS"))
        reset = self.match(draw, "FINALS", 2)
        self.assertEqual(reset.status, Match.Status.NOT_REQUIRED)
        self.assertTrue(all(s.resolved_entry_id for s in reset.slots.all()))
        with self.assertRaises(ValidationError):
            self.finish(competition, reset)
        competition.refresh_from_db()
        with self.assertRaises(ValidationError):
            commands.save_match_progress(
                actor=self.actor,
                match_id=reset.pk,
                expected_revision=competition.revision,
                side_one_score=0,
                side_two_score=0,
            )

    def test_upper_double_forfeit_structural_final_bye_does_not_activate_reset(self):
        competition, draw = self.draw(4)
        self.finish(competition, self.match(draw, "UPPER", match_number=1))
        self.finish(competition, self.match(draw, "UPPER", match_number=2))
        self.finish(competition, self.match(draw, "LOWER"))
        self.finish(competition, self.match(draw, "UPPER", 2), outcome="DOUBLE_FORFEIT")
        final = self.match(draw, "FINALS")
        self.assertEqual(final.outcome, Match.Outcome.BYE)
        self.assertEqual(
            self.match(draw, "FINALS", 2).status, Match.Status.NOT_REQUIRED
        )
        self.assertEqual(
            Stage.objects.get(pk=draw.stage_id).status, Stage.Status.COMPLETE
        )

    def test_deciding_final_double_forfeit_completes_without_champion(self):
        for policy in ("RESET", "NO_RESET"):
            with self.subTest(policy=policy), transaction.atomic():
                competition, draw = self.draw(2, policy)
                self.finish(competition, self.match(draw, "UPPER"))
                self.finish(
                    competition, self.match(draw, "FINALS"), outcome="DOUBLE_FORFEIT"
                )
                stage = Stage.objects.get(pk=draw.stage_id)
                self.assertEqual(stage.status, Stage.Status.COMPLETE)
                self.assertTrue(stage.completed_without_champion)
                transaction.set_rollback(True)
        competition, draw = self.draw(2)
        self.finish(competition, self.match(draw, "UPPER"))
        self.finish(competition, self.match(draw, "FINALS"), 2)
        self.assertEqual(
            Stage.objects.get(pk=draw.stage_id).status, Stage.Status.IN_PROGRESS
        )
        self.finish(
            competition, self.match(draw, "FINALS", 2), outcome="DOUBLE_FORFEIT"
        )
        stage = Stage.objects.get(pk=draw.stage_id)
        self.assertEqual(stage.status, Stage.Status.COMPLETE)
        self.assertTrue(stage.completed_without_champion)

    def test_publication_rejects_cross_draw_source_and_wrong_seed(self):
        competition, old_draw = self.draw(publish=False)
        competition.refresh_from_db()
        draw = commands.save_elimination_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            entrant_order=list(competition.entrants.values_list("pk", flat=True)),
        )
        slot = self.match(draw, "LOWER").slots.get(position=1)
        original = slot.source_match_id
        slot.source_match = self.match(old_draw, "UPPER")
        slot.save(update_fields=("source_match",))
        with self.assertRaises(ValidationError):
            self.publish(competition)
        slot.source_match_id = original
        slot.save(update_fields=("source_match",))
        direct = self.match(draw, "UPPER").slots.get(position=1)
        direct.entry = draw.entries.get(seed=2)
        direct.save(update_fields=("entry",))
        with self.assertRaises(ValidationError):
            self.publish(competition)

    def test_maximum_supported_field_persists_and_publishes(self):
        competition, draw = self.draw(256)
        self.assertEqual(Match.objects.filter(round__draw=draw).count(), 511)
        self.assertEqual(draw.entries.count(), 256)
        self.assertEqual(self.match(draw, "FINALS", 2).status, Match.Status.CONDITIONAL)
        self.assertEqual(len(commands._ordered_matches(draw)), 511)

    def test_lower_forfeit_eliminates_loser_and_preserves_partial_scores(self):
        competition, draw = self.draw(4)
        self.finish(competition, self.match(draw, "UPPER", match_number=1))
        self.finish(competition, self.match(draw, "UPPER", match_number=2))
        lower = self.match(draw, "LOWER")
        loser = lower.slots.get(position=2).resolved_entry_id
        competition.refresh_from_db()
        commands.finalize_match(
            actor=self.actor,
            match_id=lower.pk,
            expected_revision=competition.revision,
            outcome="FORFEIT",
            winner_position=1,
            side_one_score=0,
            side_two_score=1,
        )
        lower.refresh_from_db()
        self.assertEqual((lower.side_one_score, lower.side_two_score), (0, 1))
        self.assertFalse(lower.dependent_slots.filter(source_outcome="LOSER").exists())
        self.assertFalse(
            MatchSlot.objects.filter(
                match__round__draw=draw,
                match__status="PENDING",
                resolved_entry_id=loser,
            ).exists()
        )

    def complete_reset_draw(self):
        competition, draw = self.draw(4)
        for section, number, match_number, position in (
            ("UPPER", 1, 1, 1),
            ("UPPER", 1, 2, 1),
            ("UPPER", 2, 1, 1),
            ("LOWER", 1, 1, 1),
            ("LOWER", 2, 1, 1),
            ("FINALS", 1, 1, 2),
            ("FINALS", 2, 1, 1),
        ):
            self.finish(
                competition, self.match(draw, section, number, match_number), position
            )
        return competition, draw

    def correction(self, competition, match, position=2, **result):
        competition.refresh_from_db()
        return commands.preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            **(
                result
                or {
                    "outcome": "PLAYED",
                    "side_one_score": 2 if position == 1 else 0,
                    "side_two_score": 2 if position == 2 else 0,
                }
            ),
        )

    def apply(self, preview):
        return commands.apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Correct reported result",
        )

    def test_upper_correction_clears_both_brackets_and_retains_old_results(self):
        competition, draw = self.complete_reset_draw()
        source = self.match(draw, "UPPER")
        unaffected = self.match(draw, "UPPER", match_number=2)
        before = commands._match_snapshot(unaffected)
        preview = self.correction(competition, source)
        affected = set(
            Match.objects.filter(round__draw=draw)
            .exclude(pk__in=[source.pk, unaffected.pk])
            .values_list("pk", flat=True)
        )
        self.assertEqual({m["match_id"] for m in preview["affected_matches"]}, affected)
        reset = self.match(draw, "FINALS", 2)
        self.assertIn("reset_final_changes", preview)
        self.assertEqual(
            preview["reset_final_changes"],
            [
                {
                    "match_id": reset.pk,
                    "match_code": reset.code,
                    "before": "ACTIVE",
                    "after": "CONDITIONAL",
                }
            ],
        )
        self.assertEqual(
            commands.review_correction_preview(
                actor=self.actor, token=preview["token"]
            ),
            preview,
        )
        self.apply(preview)
        for match in Match.objects.filter(pk__in=affected):
            self.assertIn(match.status, ("PENDING", "CONDITIONAL"))
            self.assertEqual(match.outcome, "")
            for field in (
                "started_at",
                "completed_at",
                "applied_series_length",
                "winner_id",
                "side_one_score",
                "side_two_score",
            ):
                self.assertIsNone(getattr(match, field), (match.code, field))
        unaffected.refresh_from_db()
        self.assertEqual(commands._match_snapshot(unaffected), before)
        change = competition.changes.get(kind="result_corrected")
        self.assertEqual(
            {m["match_id"] for m in change.public_data["reset_matches"]}, affected
        )
        self.assertTrue(
            all(
                m["side_one_score"] is not None
                for m in change.public_data["reset_matches"]
            )
        )
        for snapshot in change.private_data["reset_matches"]:
            self.assertEqual(snapshot.get("applied_series_length"), 3)
            self.assertIsNotNone(snapshot.get("started_at"))
            self.assertIsNotNone(snapshot.get("completed_at"))
        self.assertEqual(
            change.public_data["reset_final_changes"], preview["reset_final_changes"]
        )
        self.assertEqual(
            change.private_data["reset_final_changes"], preview["reset_final_changes"]
        )
        stage = Stage.objects.get(pk=draw.stage_id)
        self.assertEqual(stage.status, Stage.Status.IN_PROGRESS)
        self.assertIsNone(stage.champion_id)
        self.assertIsNone(stage.completed_at)

    def test_first_final_correction_records_activation_of_unplayed_reset(self):
        competition, draw = self.draw(2)
        self.finish(competition, self.match(draw, "UPPER"))
        final = self.match(draw, "FINALS")
        self.finish(competition, final)
        reset = self.match(draw, "FINALS", 2)
        preview = self.correction(competition, final)
        self.assertIn("reset_final_changes", preview)
        self.assertEqual(
            preview["reset_final_changes"],
            [
                {
                    "match_id": reset.pk,
                    "match_code": reset.code,
                    "before": "NOT_REQUIRED",
                    "after": "ACTIVE",
                }
            ],
        )
        self.apply(preview)
        reset.refresh_from_db()
        self.assertEqual(reset.status, "PENDING")
        change = competition.changes.get(kind="result_corrected")
        self.assertEqual(
            change.public_data["reset_final_changes"], preview["reset_final_changes"]
        )
        self.assertEqual(
            change.private_data["reset_final_changes"], preview["reset_final_changes"]
        )
        self.assertEqual(change.public_data["reset_matches"], [])
        self.assertEqual(Stage.objects.get(pk=draw.stage_id).status, "IN_PROGRESS")

    def test_first_final_correction_deactivates_played_reset(self):
        competition, draw = self.complete_reset_draw()
        reset = self.match(draw, "FINALS", 2)
        snapshot = commands._match_snapshot(reset)
        preview = self.correction(competition, self.match(draw, "FINALS"), position=1)
        self.assertIn("reset_final_changes", preview)
        self.assertEqual(preview["reset_final_changes"][0]["after"], "NOT_REQUIRED")
        self.apply(preview)
        reset.refresh_from_db()
        self.assertEqual(reset.status, "NOT_REQUIRED")
        self.assertIsNone(reset.started_at)
        self.assertIsNone(reset.completed_at)
        self.assertIsNone(reset.applied_series_length)
        self.assertIsNone(reset.side_one_score)
        self.assertIsNone(reset.side_two_score)
        self.assertIsNone(reset.winner_id)
        self.assertEqual(reset.outcome, "")
        self.assertEqual(
            competition.changes.get(kind="result_corrected").public_data[
                "reset_matches"
            ],
            [snapshot],
        )
        stage = Stage.objects.get(pk=draw.stage_id)
        self.assertEqual(stage.status, "COMPLETE")
        self.assertEqual(
            stage.champion_id, self.match(draw, "FINALS").winner.entrant_id
        )

    def test_score_only_correction_preserves_every_downstream_result(self):
        competition, draw = self.complete_reset_draw()
        source = self.match(draw, "UPPER")
        before = list(
            Match.objects.filter(round__draw=draw).exclude(pk=source.pk).values()
        )
        preview = self.correction(
            competition, source, outcome="PLAYED", side_one_score=2, side_two_score=1
        )
        self.assertEqual(preview["affected_matches"], [])
        self.assertIn("reset_final_changes", preview)
        self.assertEqual(preview["reset_final_changes"], [])
        self.apply(preview)
        self.assertEqual(
            list(Match.objects.filter(round__draw=draw).exclude(pk=source.pk).values()),
            before,
        )

    def test_reset_impact_is_signed_and_recomputed_even_without_revision_change(self):
        from django.core import signing

        competition, draw = self.complete_reset_draw()
        preview = self.correction(competition, self.match(draw, "FINALS"), position=1)
        payload = signing.loads(preview["token"], salt=commands.CORRECTION_SALT)
        self.assertIn("reset_final_changes", payload)
        payload["reset_final_changes"] = []
        forged = signing.dumps(payload, salt=commands.CORRECTION_SALT, compress=True)
        for operation in (
            commands.review_correction_preview,
            commands.apply_correction,
        ):
            kwargs = (
                {"internal_reason": "Tampered impact"}
                if operation == commands.apply_correction
                else {}
            )
            with self.assertRaisesMessage(ValidationError, "impact changed"):
                operation(actor=self.actor, token=forged, **kwargs)
        self.assertFalse(competition.changes.filter(kind="result_corrected").exists())
        Match.objects.filter(pk=self.match(draw, "FINALS", 2).pk).update(
            status="NOT_REQUIRED"
        )
        with self.assertRaisesMessage(ValidationError, "impact changed"):
            self.apply(preview)

    def test_automatic_byes_preserve_played_finals_with_unchanged_ordered_entrants(
        self,
    ):
        competition, draw = self.draw(4)
        for section, number, match_number, position in (
            ("UPPER", 1, 1, 1),
            ("UPPER", 1, 2, 1),
            ("UPPER", 2, 1, 2),
            ("LOWER", 1, 1, 2),
            ("LOWER", 2, 1, 1),
            ("FINALS", 1, 1, 2),
            ("FINALS", 2, 1, 1),
        ):
            self.finish(
                competition, self.match(draw, section, number, match_number), position
            )
        finals = list(
            Match.objects.filter(round__draw=draw, round__section="FINALS").values()
        )
        champion = Stage.objects.get(pk=draw.stage_id).champion_id
        preview = self.correction(
            competition, self.match(draw, "UPPER"), outcome="DOUBLE_FORFEIT"
        )
        expected = {
            self.match(draw, "UPPER", 2).pk,
            self.match(draw, "LOWER").pk,
            self.match(draw, "LOWER", 2).pk,
        }
        self.assertEqual(
            {item["match_id"] for item in preview["affected_matches"]}, expected
        )
        self.assertEqual(preview["reset_final_changes"], [])
        self.apply(preview)
        self.assertEqual(
            list(
                Match.objects.filter(round__draw=draw, round__section="FINALS").values()
            ),
            finals,
        )
        for match in Match.objects.filter(pk__in=expected):
            self.assertEqual(match.outcome, "BYE")
            self.assertIsNone(match.side_one_score)
            self.assertIsNone(match.side_two_score)
            self.assertIsNone(match.started_at)
            self.assertIsNone(match.applied_series_length)
        stage = Stage.objects.get(pk=draw.stage_id)
        self.assertEqual(stage.champion_id, champion)
        self.assertEqual(stage.status, "COMPLETE")
