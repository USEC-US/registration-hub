from copy import copy
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from competitions import commands, swiss_commands
from competitions.models import CompetitionEntrant, Match, MatchSlot, Round, StageDraw
from competitions.tests import test_swiss_plan as fixtures


class SwissCommandTests(TestCase):
    setUp = fixtures.SwissPlanTests.setUp
    _registration = fixtures.SwissPlanTests._registration
    _competition = fixtures.SwissPlanTests._competition
    _swiss = fixtures.SwissPlanTests._swiss
    _elimination = fixtures.SwissPlanTests._elimination

    def _revision(self):
        self.competition.refresh_from_db()
        return self.competition.revision

    def _draw(self, count=5, *, publish=True, **rules):
        self._competition(count)
        self.stage = self._swiss(**(dict(advancement_count=2) | rules))
        self._elimination(2)
        draw = swiss_commands.save_swiss_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
            ordered_entrant_ids=[e.pk for e in self.entrants],
        )
        if publish:
            commands.publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self._revision(),
            )
            draw.refresh_from_db()
        return draw

    def _finish(self, round_):
        for match in round_.matches.exclude(status="FINAL"):
            commands.finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self._revision(),
                outcome="PLAYED",
                side_one_score=2,
                side_two_score=0,
            )

    def _generate(self, **options):
        return swiss_commands.generate_swiss_round(
            actor=self.actor,
            stage_id=self.stage.pk,
            expected_revision=self._revision(),
            **options,
        )

    def _publish(self, round_):
        return swiss_commands.publish_swiss_round(
            actor=self.actor, round_id=round_.pk, expected_revision=self._revision()
        )

    def _points(self, draw):
        return {
            r.entry_id: (r.points, r.wins, r.bye_count)
            for r in swiss_commands.swiss_standings(draw)
        }

    def test_draw_creation_saves_only_round_one_and_actual_limit(self):
        draw = self._draw(publish=False)
        self.assertEqual(draw.swiss_round_limit, 3)
        round_ = draw.rounds.get()
        self.assertEqual((round_.number, round_.version, round_.state), (1, 1, "DRAFT"))
        self.assertEqual(round_.matches.count(), 3)
        self.assertEqual(MatchSlot.objects.filter(match__round=round_).count(), 6)
        self.assertFalse(round_.matches.exclude(status="PENDING").exists())
        self.assertTrue(all(v == (0, 0, 0) for v in self._points(draw).values()))
        commands.publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
        )
        round_.refresh_from_db()
        self.assertEqual(round_.state, "PUBLISHED")
        self.assertEqual(
            round_.matches.filter(outcome="BYE", status="FINAL").count(), 1
        )
        self.assertEqual(
            sum(r.bye_count for r in swiss_commands.swiss_standings(draw)), 1
        )

    def test_generation_requires_final_prior_round_and_never_autogenerates(self):
        draw = self._draw()
        with self.assertRaises(ValidationError):
            self._generate()
        self._finish(draw.rounds.get(number=1))
        self.assertEqual(draw.rounds.count(), 1)
        self.stage.refresh_from_db()
        self.assertNotEqual(self.stage.status, "COMPLETE")
        self.assertIsNone(self.stage.champion_id)
        next_round = self._generate()
        self.assertEqual((next_round.number, next_round.state), (2, "DRAFT"))
        self._publish(next_round)
        self._finish(next_round)
        self.assertEqual(draw.rounds.count(), 2)
        self.assertEqual(draw.rounds.filter(state="PUBLISHED").count(), 2)

    def test_repeated_generate_reuses_draft_without_solver_or_revision_change(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        saved = self._generate()
        revision = self._revision()
        with patch.object(
            swiss_commands,
            "pair_swiss_round",
            side_effect=AssertionError("solver invoked"),
        ):
            self.assertEqual(self._generate().pk, saved.pk)
            swiss_commands.swiss_standings(draw)
        self.assertEqual(self._revision(), revision)
        self.assertEqual(draw.rounds.count(), 2)
        self.assertEqual(
            self.competition.changes.get(revision=revision).public_data, {}
        )

    def test_explicit_regeneration_retains_ids_and_appends_codes(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        old = self._generate()
        old_ids = list(old.matches.values_list("pk", flat=True))
        regenerated = self._generate(regenerate=True)
        old.refresh_from_db()
        self.assertEqual(old.state, "SUPERSEDED")
        self.assertEqual(regenerated.version, 2)
        self.assertEqual(list(old.matches.values_list("pk", flat=True)), old_ids)
        self.assertEqual(
            list(regenerated.matches.values_list("code", flat=True)),
            [f"Swiss 1-M{i}" for i in (7, 8, 9)],
        )
        self._publish(regenerated)
        self.assertEqual(len(commands._ordered_matches(draw)), 6)
        commands._validate_saved_draw(draw)

    def test_draft_bye_has_no_current_credit_and_publication_credits_once(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        before = self._points(draw)
        draft = self._generate()
        bye = draft.matches.get(slots__is_empty=True)
        self.assertEqual(before, self._points(draw))
        with self.assertRaises(ValidationError):
            commands.start_match(
                actor=self.actor, match_id=bye.pk, expected_revision=self._revision()
            )
        entry_id = bye.slots.get(position=1).entry_id
        self._publish(draft)
        after = self._points(draw)
        self.assertEqual(after[entry_id][1], before[entry_id][1] + 1)
        with self.assertRaises(ValidationError):
            self._publish(draft)
        self.assertEqual(after, self._points(draw))

    def test_final_private_bye_cannot_contribute_standings(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        before = self._points(draw)
        draft = self._generate()
        bye = draft.matches.get(slots__is_empty=True)
        Match.objects.filter(pk=bye.pk).update(
            status="FINAL", outcome="BYE", winner_id=bye.slots.get(position=1).entry_id
        )
        self.assertEqual(before, self._points(draw))

    def test_private_and_superseded_rounds_reject_all_mutation_entrypoints(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        draft = self._generate()
        match = draft.matches.first()
        for state in ("DRAFT", "SUPERSEDED"):
            Round.objects.filter(pk=draft.pk).update(state=state)
            for operation, values in (
                (commands.schedule_match, {"scheduled_at": timezone.now()}),
                (commands.start_match, {}),
                (
                    commands.save_match_progress,
                    {"side_one_score": 1, "side_two_score": 0},
                ),
                (
                    commands.finalize_match,
                    {"outcome": "PLAYED", "side_one_score": 2, "side_two_score": 0},
                ),
                (commands.set_match_series_length, {"series_length": 5}),
                (
                    commands.preview_correction,
                    {"outcome": "PLAYED", "side_one_score": 0, "side_two_score": 2},
                ),
            ):
                with (
                    self.subTest(state=state, operation=operation.__name__),
                    self.assertRaises(ValidationError),
                ):
                    operation(
                        actor=self.actor,
                        match_id=match.pk,
                        expected_revision=self._revision(),
                        **values,
                    )
            with self.assertRaises(ValidationError):
                commands.set_round_series_length(
                    actor=self.actor,
                    round_id=draft.pk,
                    expected_revision=self._revision(),
                    series_length=5,
                )

    def test_correction_review_and_apply_reject_superseded_round(self):
        draw = self._draw()
        round_ = draw.rounds.get()
        self._finish(round_)
        match = round_.matches.exclude(outcome="BYE").first()
        preview = commands.preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self._revision(),
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        Round.objects.filter(pk=round_.pk).update(state="SUPERSEDED")
        with self.assertRaises(ValidationError):
            commands.review_correction_preview(actor=self.actor, token=preview["token"])
        with self.assertRaises(ValidationError):
            commands.apply_correction(
                actor=self.actor, token=preview["token"], internal_reason="Wrong result"
            )

    def test_stale_generation_revision_has_no_side_effects(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        revision = self._revision()
        with self.assertRaises(ValidationError):
            swiss_commands.generate_swiss_round(
                actor=self.actor, stage_id=self.stage.pk, expected_revision=revision - 1
            )
        self.assertEqual(draw.rounds.count(), 1)
        self.assertEqual(self._revision(), revision)

    def test_initial_publication_rejects_stale_source_and_draw_limit_tampering(self):
        draw = self._draw(publish=False)
        Round.objects.filter(draw=draw).update(source_fingerprint="bad")
        with self.assertRaises(ValidationError):
            commands.publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self._revision(),
            )
        draw = swiss_commands.save_swiss_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
            ordered_entrant_ids=[e.pk for e in self.entrants],
        )
        StageDraw.objects.filter(pk=draw.pk).update(swiss_round_limit=2)
        with self.assertRaises(ValidationError):
            commands.publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self._revision(),
            )
        self.assertFalse(self.stage.draws.filter(state="PUBLISHED").exists())

    def test_saved_round_becomes_stale_after_confirmed_result_changes(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        saved = self._generate()
        match = draw.rounds.get(number=1).matches.exclude(outcome="BYE").first()
        Match.objects.filter(pk=match.pk).update(side_one_score=2, side_two_score=1)
        with self.assertRaises(ValidationError):
            self._publish(saved)
        with self.assertRaises(ValidationError):
            self._generate()

    def test_scheduling_is_excluded_from_source_fingerprint(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        saved = self._generate()
        Match.objects.filter(round__draw=draw).update(scheduled_at=timezone.now())
        self._publish(saved)
        saved.refresh_from_db()
        self.assertEqual(saved.state, "PUBLISHED")

    def test_publication_rechecks_approval_and_selection(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        saved = self._generate()
        registration = self.entrants[0].registration
        registration.status = "REJECTED"
        registration.save(update_fields=("status",))
        with self.assertRaises(ValidationError):
            self._publish(saved)
        registration.status = "APPROVED"
        registration.save(update_fields=("status",))
        CompetitionEntrant.objects.filter(pk=self.entrants[0].pk).update(
            is_selected=False
        )
        with self.assertRaises(ValidationError):
            self._publish(saved)
        saved.refresh_from_db()
        self.assertEqual(saved.state, "DRAFT")

    def test_publication_rejects_duplicate_foreign_missing_and_custom_pairs(self):
        draw = self._draw(6, publish=False)
        slots = list(
            MatchSlot.objects.filter(match__round__draw=draw, position=2).order_by(
                "match__number"
            )
        )
        original = slots[0].entry_id
        for entry_id in (slots[1].entry_id, None):
            MatchSlot.objects.filter(pk=slots[0].pk).update(
                entry_id=entry_id, resolved_entry_id=entry_id, is_empty=entry_id is None
            )
            with self.assertRaises(ValidationError):
                commands.publish_draw(
                    actor=self.actor,
                    competition_id=self.competition.pk,
                    expected_revision=self._revision(),
                )
        foreign = StageDraw.objects.create(
            stage=self.stage, version=9, state="SUPERSEDED"
        )
        entry = foreign.entries.create(entrant=self.entrants[0], seed=1)
        MatchSlot.objects.filter(pk=slots[0].pk).update(
            entry=entry, resolved_entry=entry, is_empty=False
        )
        with self.assertRaises(ValidationError):
            commands.publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self._revision(),
            )
        MatchSlot.objects.filter(pk=slots[0].pk).update(
            entry_id=slots[1].entry_id, resolved_entry_id=slots[1].entry_id
        )
        MatchSlot.objects.filter(pk=slots[1].pk).update(
            entry_id=original, resolved_entry_id=original
        )
        with self.assertRaises(ValidationError):
            commands.publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self._revision(),
            )

    def _rematch_dead_end(self):
        draw = self._draw(
            4,
            format="SWISS_THRESHOLD",
            win_target=2,
            loss_limit=2,
            advancement_count=None,
        )
        self._finish(draw.rounds.get())
        second = self._generate()
        self._publish(second)
        self._finish(second)
        return draw

    def test_no_rematch_dead_end_is_atomic_and_override_needs_explicit_reason(self):
        draw = self._rematch_dead_end()
        revision = self._revision()
        for values in (
            {},
            {"allow_rematches": True},
            {"allow_rematches": True, "internal_reason": "  "},
            {"allow_rematches": "true", "internal_reason": "Confirmed"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self._generate(**values)
            self.assertEqual(draw.rounds.count(), 2)
            self.assertEqual(self._revision(), revision)
        saved = self._generate(
            allow_rematches=True, internal_reason="Confirmed rematch exception"
        )
        self.assertTrue(saved.rematches_authorized)
        audit = self.competition.changes.get(revision=self._revision())
        self.assertEqual(audit.internal_reason, "Confirmed rematch exception")
        self.assertEqual(audit.public_data, {})
        self._publish(saved)

    def test_publication_rejects_rematch_authorization_tampering(self):
        draw = self._draw(4)
        self._finish(draw.rounds.get())
        saved = self._generate()
        Round.objects.filter(pk=saved.pk).update(rematches_authorized=True)
        with self.assertRaises(ValidationError):
            self._publish(saved)

    def test_feasible_round_stays_repeat_free_even_with_override_flag(self):
        draw = self._draw(6)
        self._finish(draw.rounds.get())
        saved = self._generate(
            allow_rematches=True, internal_reason="Permission only if needed"
        )
        first = {
            frozenset(m.slots.values_list("entry_id", flat=True))
            for m in draw.rounds.get(number=1).matches.all()
        }
        later = {
            frozenset(m.slots.values_list("entry_id", flat=True))
            for m in saved.matches.all()
        }
        self.assertFalse(first & later)
        self._publish(saved)

    def test_storage_budget_counts_retained_matches_before_persisting(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        old = self._generate()
        saved = self._generate(regenerate=True)
        old.refresh_from_db()
        self.assertEqual(old.state, "SUPERSEDED")
        with (
            patch.object(swiss_commands, "MAX_MATCHES", 11),
            self.assertRaises(ValidationError),
        ):
            self._generate(regenerate=True)
        saved.refresh_from_db()
        self.assertEqual(saved.state, "DRAFT")
        self.assertEqual(draw.rounds.count(), 3)

    def test_round_limit_blocks_further_generation(self):
        draw = self._draw(4, round_count=1)
        self._finish(draw.rounds.get())
        with self.assertRaises(ValidationError):
            self._generate()

    def test_threshold_rejects_nondecisive_overrides_at_command_boundary(self):
        draw = self._draw(
            4,
            format="SWISS_THRESHOLD",
            win_target=2,
            loss_limit=2,
            advancement_count=None,
        )
        round_ = draw.rounds.get()
        match = round_.matches.first()
        with self.assertRaises(ValidationError):
            commands.set_round_series_length(
                actor=self.actor,
                round_id=round_.pk,
                expected_revision=self._revision(),
                series_length=2,
            )
        with self.assertRaises(ValidationError):
            commands.set_match_series_length(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self._revision(),
                series_length=2,
            )
        Match.objects.filter(pk=match.pk).update(
            applied_series_mode="FIXED_GAMES", series_length_override=2
        )
        for command, values in (
            (commands.start_match, {}),
            (commands.save_match_progress, {"side_one_score": 0, "side_two_score": 0}),
            (
                commands.finalize_match,
                {"outcome": "PLAYED", "side_one_score": 1, "side_two_score": 1},
            ),
        ):
            with (
                self.subTest(command=command.__name__),
                self.assertRaises(ValidationError),
            ):
                command(
                    actor=self.actor,
                    match_id=match.pk,
                    expected_revision=self._revision(),
                    **values,
                )

    def test_standings_accept_stage_local_projected_matches(self):
        draw = self._draw(4)
        match = draw.rounds.get().matches.first()
        projected = copy(match)
        projected.status = "FINAL"
        projected.outcome = "PLAYED"
        projected.side_one_score, projected.side_two_score = 2, 0
        projected.winner_id = match.slots.get(position=1).entry_id
        rows = swiss_commands.swiss_standings(draw, projected_matches=[projected])
        self.assertEqual(sum(r.played for r in rows), 2)
        self.assertEqual(sum(r.wins for r in rows), 1)
        self.assertTrue(
            all(r.played == 0 for r in swiss_commands.swiss_standings(draw))
        )

    def test_forfeits_contribute_no_fabricated_game_metrics(self):
        draw = self._draw(4)
        matches = list(draw.rounds.get().matches.all())
        commands.finalize_match(
            actor=self.actor,
            match_id=matches[0].pk,
            expected_revision=self._revision(),
            outcome="DOUBLE_FORFEIT",
            side_one_score=1,
            side_two_score=1,
        )
        commands.finalize_match(
            actor=self.actor,
            match_id=matches[1].pk,
            expected_revision=self._revision(),
            outcome="FORFEIT",
            winner_position=1,
            side_one_score=1,
            side_two_score=0,
        )
        rows = swiss_commands.swiss_standings(draw)
        self.assertEqual(sum(r.losses for r in rows), 3)
        self.assertEqual(sum(r.points for r in rows), 3)
        self.assertTrue(all(r.games_won == 0 and r.game_difference == 0 for r in rows))

    def test_pairing_fingerprint_is_stage_local_across_provenance_and_revision_changes(
        self,
    ):
        draw = self._draw()
        self._finish(draw.rounds.get())
        before = swiss_commands._swiss_source_fingerprint(draw, 2)
        draw.source_fingerprint = "refreshed predecessor qualification"
        draw.source_draw_id = 9999
        self.competition.revision += 10
        Match.objects.filter(round__draw=draw).update(scheduled_at=timezone.now())
        self.assertEqual(before, swiss_commands._swiss_source_fingerprint(draw, 2))

    def test_saved_draw_validation_excludes_extra_contests_from_ordinary_rounds(self):
        draw = self._draw()
        Round.objects.create(
            draw=draw,
            number=1,
            section="TIEBREAK",
            state="PUBLISHED",
            published_at=timezone.now(),
        )
        commands._validate_saved_draw(draw)

    def test_stale_publication_revision_leaves_preview_private(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        saved = self._generate()
        revision = self._revision()
        with self.assertRaises(ValidationError):
            swiss_commands.publish_swiss_round(
                actor=self.actor, round_id=saved.pk, expected_revision=revision - 1
            )
        saved.refresh_from_db()
        self.assertEqual(saved.state, "DRAFT")
        self.assertEqual(self._revision(), revision)
