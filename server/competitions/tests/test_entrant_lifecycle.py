from unittest.mock import patch

from django.core import signing
from django.core.exceptions import ValidationError
from django.test import TestCase

from competitions import commands
from competitions.tests import test_double_elimination_commands as de_fixtures
from competitions.tests import test_round_robin_commands as rr_fixtures
from competitions.tests import test_swiss_commands as swiss_fixtures
from competitions.tests import test_handoffs as handoff_fixtures
from competitions.handoff_commands import generate_next_stage_draw
from competitions.models import Match
from competitions.tests import test_commands as fixtures
from competitions.lifecycle_commands import (
    apply_entrant_transition,
    preview_entrant_transition,
    review_lifecycle_preview,
)


class EntrantLifecycleTests(TestCase):
    setUp = fixtures.CompetitionCommandTests.setUp
    _registration = fixtures.CompetitionCommandTests._registration
    _published_draw = fixtures.CompetitionCommandTests._published_draw

    def setup_draw(self):
        self.competition, self.draw = self._published_draw()
        self.match = self.draw.rounds.get(number=1).matches.get(number=2)
        self.entrant = self.match.slots.get(position=1).resolved_entry.entrant

    def preview(self, entrant=None, status="WITHDRAWN"):
        self.competition.refresh_from_db()
        return preview_entrant_transition(
            actor=self.actor,
            entrant_id=(entrant or self.entrant).pk,
            expected_revision=self.competition.revision,
            status=status,
        )

    def apply(self, preview, **options):
        return apply_entrant_transition(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Private medical explanation",
            **options,
        )

    def transition(self, entrant=None, status="WITHDRAWN"):
        return self.apply(
            self.preview(entrant, status),
            confirm_live_forfeits=True,
            confirm_resets=True,
        )

    def test_preview_read_only_signed_apply_and_duplicate(self):
        self.setup_draw()
        revision = self.competition.revision
        before = list(Match.objects.values())
        preview = self.preview()
        self.assertEqual(before, list(Match.objects.values()))
        self.assertEqual(
            review_lifecycle_preview(actor=self.actor, token=preview["token"]), preview
        )
        self.transition()
        self.match.refresh_from_db()
        self.entrant.refresh_from_db()
        self.assertEqual(self.match.outcome, "FORFEIT")
        self.assertEqual(self.entrant.status, "WITHDRAWN")
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.revision, revision + 1)
        self.assertEqual(self.entrant.removal_change.kind, "entrant_withdrawn")
        with self.assertRaises(ValidationError):
            self.apply(preview)

    def test_live_forfeit_requires_consent_and_restores_partial_score(self):
        self.setup_draw()
        commands.start_match(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.save_match_progress(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            side_one_score=1,
            side_two_score=0,
        )
        preview = self.preview()
        self.assertEqual(preview["live_forfeit_ids"], [self.match.pk])
        with self.assertRaises(ValidationError):
            self.apply(preview)
        self.apply(preview, confirm_live_forfeits=True)
        self.entrant.refresh_from_db()
        history = self.entrant.removal_change.private_data
        restore = self.preview(status="ACTIVE")
        with self.assertRaises(ValidationError):
            self.apply(restore)
        self.apply(restore, confirm_resets=True)
        self.match.refresh_from_db()
        self.entrant.refresh_from_db()
        self.assertEqual(self.entrant.status, "ACTIVE")
        self.assertEqual(self.match.status, "LIVE")
        self.assertEqual((self.match.side_one_score, self.match.side_two_score), (1, 0))
        self.assertEqual(history["match_impacts"][0]["after"]["outcome"], "FORFEIT")

    def test_two_removals_restore_in_either_order(self):
        self.setup_draw()
        other = self.match.slots.get(position=2).resolved_entry.entrant
        for first, second in ((self.entrant, other), (other, self.entrant)):
            self.transition(first)
            self.transition(second, "DISQUALIFIED")
            self.match.refresh_from_db()
            self.assertEqual(self.match.outcome, "DOUBLE_FORFEIT")
            self.transition(first, "ACTIVE")
            self.match.refresh_from_db()
            self.assertEqual(self.match.outcome, "FORFEIT")
            self.assertEqual(self.match.winner.entrant_id, first.pk)
            self.transition(second, "ACTIVE")
            self.match.refresh_from_db()
            self.assertEqual(self.match.status, "PENDING")

    def test_inactive_relabel_preserves_original_removal(self):
        self.setup_draw()
        self.transition()
        self.entrant.refresh_from_db()
        original = self.entrant.removal_change_id
        state = list(Match.objects.values())
        self.transition(status="DISQUALIFIED")
        self.entrant.refresh_from_db()
        self.assertEqual(self.entrant.removal_change_id, original)
        self.assertEqual(state, list(Match.objects.values()))
        self.assertEqual(
            self.competition.changes.latest("revision").kind, "entrant_status_changed"
        )

    def test_restore_preserves_manual_correction(self):
        self.setup_draw()
        self.transition()
        self.competition.refresh_from_db()
        correction = commands.preview_correction(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        commands.apply_correction(
            actor=self.actor,
            token=correction["token"],
            internal_reason="Independent correction",
        )
        preview = self.preview(status="ACTIVE")
        self.assertIn(self.match.pk, preview["preserved_corrections"])
        self.apply(preview, confirm_resets=True)
        self.match.refresh_from_db()
        self.assertEqual(self.match.outcome, "PLAYED")

    def test_validation_and_failure_are_atomic(self):
        self.setup_draw()
        for value in (None, True, [], "UNKNOWN", "ACTIVE"):
            with self.assertRaises(ValidationError):
                self.preview(status=value)
        preview = self.preview()
        for reason in (None, 2, "", "   "):
            with self.assertRaises(ValidationError):
                apply_entrant_transition(
                    actor=self.actor, token=preview["token"], internal_reason=reason
                )
        for consent in (1, "true", None):
            with self.assertRaises(ValidationError):
                self.apply(preview, confirm_resets=consent)
        with self.assertRaises(ValidationError):
            self.apply(dict(preview, token=preview["token"] + "tamper"))
        data = signing.loads(preview["token"], salt="competitions.lifecycle")
        data["entrant_id"] = (
            self.draw.entries.exclude(entrant=self.entrant).first().entrant_id
        )
        with self.assertRaises(ValidationError):
            self.apply(
                dict(preview, token=signing.dumps(data, salt="competitions.lifecycle"))
            )
        before = list(Match.objects.values())
        revision = self.competition.revision
        with patch(
            "competitions.lifecycle_commands._update_stage_completion",
            side_effect=RuntimeError("mid-apply"),
        ):
            with self.assertRaises(RuntimeError):
                self.apply(preview)
        self.entrant.refresh_from_db()
        self.competition.refresh_from_db()
        self.assertEqual(self.entrant.status, "ACTIVE")
        self.assertIsNone(self.entrant.removal_change_id)
        self.assertEqual(before, list(Match.objects.values()))
        self.assertEqual(revision, self.competition.revision)
        self.assertFalse(
            self.competition.changes.filter(kind="entrant_withdrawn").exists()
        )

    def test_restore_rejects_unapproved_registration_and_missing_provenance(self):
        self.setup_draw()
        self.transition()
        self.entrant.registration.status = "REJECTED"
        self.entrant.registration.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self.preview(status="ACTIVE")
        self.entrant.registration.status = "APPROVED"
        self.entrant.registration.save(update_fields=["status"])
        self.entrant.removal_change = None
        self.entrant.save(update_fields=["removal_change"])
        with self.assertRaises(ValidationError):
            self.preview(status="ACTIVE")

    def test_restore_undoes_later_removal_forfeit(self):
        self.setup_draw()
        bye_winner = self.draw.entries.get(seed=1).entrant
        self.transition(bye_winner)
        bye_winner.refresh_from_db()
        removal = bye_winner.removal_change
        original_history = removal.private_data.copy()
        self.competition.refresh_from_db()
        commands.finalize_match(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        final = self.draw.rounds.get(number=2).matches.get()
        self.assertEqual(final.outcome, "FORFEIT")
        self.assertTrue(final.removal_effect)
        history = self.competition.changes.latest("revision").private_data
        self.assertEqual(
            history["removal_effects"][str(final.pk)], final.removal_effect
        )
        removal.refresh_from_db()
        self.assertEqual(removal.private_data, original_history)
        self.transition(bye_winner, "ACTIVE")
        final.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(final.status, "PENDING")
        self.assertEqual(self.match.outcome, "PLAYED")
        self.assertEqual(
            final.slots.get(position=1).resolved_entry.entrant_id, bye_winner.pk
        )

    def test_unrelated_normal_progression_does_not_rewrite_automatic_history(self):
        self.setup_draw()
        self.transition()
        before = list(Match.objects.values())
        commands._resolve_automatic_matches(self.draw)
        self.assertEqual(before, list(Match.objects.values()))

    def test_final_before_removal_is_preserved(self):
        self.setup_draw()
        commands.finalize_match(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        self.match.refresh_from_db()
        before = self.match.__dict__.copy()
        self.transition()
        self.match.refresh_from_db()
        for field in (
            "status",
            "outcome",
            "winner_id",
            "side_one_score",
            "completed_at",
        ):
            self.assertEqual(getattr(self.match, field), before[field])

    def test_correction_propagation_records_removal_cause_and_restore(self):
        self.setup_draw()
        loser = self.match.slots.get(position=2).resolved_entry.entrant
        commands.finalize_match(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        self.transition(loser)
        self.competition.refresh_from_db()
        preview = commands.preview_correction(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        commands.apply_correction(
            actor=self.actor, token=preview["token"], internal_reason="Wrong winner"
        )
        final = self.draw.rounds.get(number=2).matches.get()
        self.assertEqual(final.outcome, "FORFEIT")
        self.assertTrue(final.removal_effect)
        event = self.competition.changes.latest("revision")
        self.assertEqual(
            event.private_data["removal_effects"][str(final.pk)], final.removal_effect
        )
        self.transition(loser, "ACTIVE")
        final.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(final.status, "PENDING")
        self.assertEqual(self.match.winner.entrant_id, loser.pk)

    def test_upstream_correction_discards_obsolete_restoration_progress(self):
        from competitions.lifecycle_commands import project_removal_results

        self.setup_draw()
        commands.finalize_match(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        final = self.draw.rounds.get(number=2).matches.get()
        original_slots = list(
            final.slots.order_by("position").values_list("resolved_entry_id", flat=True)
        )
        replacement = self.match.slots.get(position=2).resolved_entry_id
        self.competition.refresh_from_db()
        commands.start_match(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.save_match_progress(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=self.competition.revision,
            side_one_score=1,
            side_two_score=0,
        )
        self.transition()
        self.competition.refresh_from_db()
        projected = project_removal_results(
            self.draw,
            result_updates={
                self.match.pk: {
                    "status": "FINAL",
                    "outcome": "PLAYED",
                    "winner_id": replacement,
                    "side_one_score": 0,
                    "side_two_score": 2,
                }
            },
        )
        self.assertEqual(projected["reset_match_ids"], [final.pk])
        self.assertEqual(projected["matches"][final.pk]["status"], "PENDING")
        preview = commands.preview_correction(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        impact = next(i for i in preview["match_impacts"] if i["match_id"] == final.pk)
        self.assertEqual(impact["after_status"], "PENDING")
        commands.apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Correct semifinal winner",
        )
        final.refresh_from_db()
        self.assertEqual(
            list(
                final.slots.order_by("position").values_list(
                    "resolved_entry_id", flat=True
                )
            ),
            [original_slots[0], replacement],
        )
        self.assertEqual(final.status, "PENDING")
        for field in (
            "side_one_score",
            "side_two_score",
            "applied_series_length",
            "started_at",
            "completed_at",
            "winner_id",
        ):
            self.assertIsNone(getattr(final, field), field)
        self.assertEqual(final.applied_series_mode, "")
        self.assertEqual(final.outcome, "")
        self.assertEqual(
            self.competition.changes.latest("revision").private_data["reset_matches"][
                0
            ]["match_id"],
            final.pk,
        )

    def test_routed_live_before_state_survives_second_removal(self):
        self.setup_draw()
        commands.finalize_match(
            actor=self.actor,
            match_id=self.match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        final = self.draw.rounds.get(number=2).matches.get()
        before_slots = [
            list(pair)
            for pair in final.slots.order_by("position").values_list(
                "is_resolved", "resolved_entry_id"
            )
        ]
        other = final.slots.get(position=1).resolved_entry.entrant
        self.competition.refresh_from_db()
        commands.start_match(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.save_match_progress(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=self.competition.revision,
            side_one_score=1,
            side_two_score=0,
        )
        self.transition()
        self.transition(other)
        final.refresh_from_db()
        self.assertEqual(final.removal_effect["before"]["slots"], before_slots)
        self.transition(status="ACTIVE")
        self.transition(other, "ACTIVE")
        final.refresh_from_db()
        self.assertEqual(
            (final.status, final.side_one_score, final.side_two_score), ("LIVE", 1, 0)
        )

    def test_scheduling_only_preserves_removal_authority(self):
        from django.utils import timezone

        self.setup_draw()
        bye_winner = self.draw.entries.get(seed=1).entrant
        self.transition(bye_winner)
        final = self.draw.rounds.get(number=2).matches.get()
        before = final.removal_effect
        self.assertTrue(before)
        when = timezone.now()
        self.competition.refresh_from_db()
        commands.schedule_match(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=self.competition.revision,
            scheduled_at=when,
        )
        final.refresh_from_db()
        self.assertEqual(final.removal_effect, before)
        self.transition(bye_winner, "ACTIVE")
        final.refresh_from_db()
        self.assertEqual(final.scheduled_at, when)
        self.assertEqual(
            final.slots.get(position=1).resolved_entry.entrant_id, bye_winner.pk
        )

    def test_restore_resets_only_played_dependent_final(self):
        self.setup_draw()
        self.transition()
        final = self.draw.rounds.get(number=2).matches.get()
        self.competition.refresh_from_db()
        commands.finalize_match(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        preview = self.preview(status="ACTIVE")
        self.assertEqual(preview["reset_match_ids"], sorted([self.match.pk, final.pk]))
        self.apply(preview, confirm_resets=True)
        final.refresh_from_db()
        self.assertEqual(final.status, "PENDING")
        self.assertIsNone(final.completed_at)
        self.assertIsNone(final.applied_series_length)
        self.assertEqual(final.applied_series_mode, "")

    def test_stale_impact_without_revision_change_is_rejected(self):
        self.setup_draw()
        preview = self.preview()
        Match.objects.filter(pk=self.match.pk).update(side_one_score=1)
        with self.assertRaises(ValidationError):
            self.apply(preview)
        self.entrant.refresh_from_db()
        self.assertEqual(self.entrant.status, "ACTIVE")

    def test_restore_rejects_incomplete_removal_history(self):
        self.setup_draw()
        self.transition()
        self.entrant.refresh_from_db()
        change = self.entrant.removal_change
        change.private_data = {"entrant_id": self.entrant.pk}
        change.save(update_fields=["private_data"])
        with self.assertRaises(ValidationError):
            self.preview(status="ACTIVE")

    def test_permissions_are_rechecked_at_apply(self):
        from django.core.exceptions import PermissionDenied

        self.setup_draw()
        preview = self.preview()
        self.actor.is_superuser = False
        self.actor.save(update_fields=["is_superuser"])
        with self.assertRaises(PermissionDenied):
            self.apply(preview)
        self.entrant.refresh_from_db()
        self.assertEqual(self.entrant.status, "ACTIVE")


class DoubleEliminationLifecycleTests(TestCase):
    setUp = fixtures.CompetitionCommandTests.setUp
    _registration = fixtures.CompetitionCommandTests._registration
    configure = de_fixtures.DoubleEliminationCommandTests.configure
    draw = de_fixtures.DoubleEliminationCommandTests.draw
    publish = de_fixtures.DoubleEliminationCommandTests.publish
    preview = EntrantLifecycleTests.preview
    apply = EntrantLifecycleTests.apply
    transition = EntrantLifecycleTests.transition

    def test_pending_and_live_removal_and_restore(self):
        self.competition, draw = self.draw()
        match = draw.rounds.get(section="UPPER", number=1).matches.first()
        self.entrant = match.slots.get(position=1).resolved_entry.entrant
        self.transition()
        match.refresh_from_db()
        self.assertEqual(match.outcome, "FORFEIT")
        self.transition(status="ACTIVE")
        match.refresh_from_db()
        self.assertEqual(match.status, "PENDING")
        self.competition.refresh_from_db()
        commands.start_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
        )
        preview = self.preview(status="DISQUALIFIED")
        self.assertEqual(preview["live_forfeit_ids"], [match.pk])
        self.apply(preview, confirm_live_forfeits=True)
        self.transition(status="ACTIVE")
        match.refresh_from_db()
        self.assertEqual(match.status, "LIVE")

    def test_private_draw_retired_and_effects_private(self):
        self.competition, draw = self.draw(publish=False)
        self.entrant = draw.entries.first().entrant
        preview = self.preview()
        self.assertEqual(preview["retired_draws"], [draw.pk])
        self.apply(preview)
        draw.refresh_from_db()
        self.assertEqual(draw.state, "SUPERSEDED")
        self.assertEqual(self.competition.changes.latest("revision").public_data, {})
        self.transition(status="ACTIVE")
        draw.refresh_from_db()
        self.assertEqual(draw.state, "SUPERSEDED")


class RoundRobinLifecycleTests(TestCase):
    setUp = fixtures.CompetitionCommandTests.setUp
    _registration = fixtures.CompetitionCommandTests._registration
    configure = rr_fixtures.RoundRobinCommandTests.configure
    setup_stage = rr_fixtures.RoundRobinCommandTests.setup_stage
    choose = rr_fixtures.RoundRobinCommandTests.choose
    draw = rr_fixtures.RoundRobinCommandTests.draw
    publish = rr_fixtures.RoundRobinCommandTests.publish
    preview = EntrantLifecycleTests.preview
    apply = EntrantLifecycleTests.apply
    transition = EntrantLifecycleTests.transition

    def test_independent_fixtures_and_live_scores_survive_restore(self):
        self.configure()
        self.choose(4)
        draw = self.draw(group_specs=[("A", 2)])
        self.publish()
        matches = Match.objects.filter(round__draw=draw)
        match = matches.first()
        self.entrant = match.slots.get(position=1).resolved_entry.entrant
        independent = matches.exclude(
            slots__resolved_entry__entrant=self.entrant
        ).first()
        self.competition.refresh_from_db()
        commands.finalize_match(
            actor=self.actor,
            match_id=independent.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=1,
            side_two_score=1,
        )
        self.competition.refresh_from_db()
        commands.start_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.save_match_progress(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            side_one_score=1,
            side_two_score=0,
        )
        independent.refresh_from_db()
        previous = independent.completed_at
        self.transition()
        match.refresh_from_db()
        self.assertEqual(match.outcome, "FORFEIT")
        self.transition(status="ACTIVE")
        match.refresh_from_db()
        independent.refresh_from_db()
        self.assertEqual(
            (match.status, match.side_one_score, match.side_two_score), ("LIVE", 1, 0)
        )
        self.assertEqual(independent.completed_at, previous)
        self.assertEqual(independent.outcome, "PLAYED")


class SwissLifecycleCommandTests(TestCase):
    setUp = swiss_fixtures.SwissCommandTests.setUp
    _registration = swiss_fixtures.SwissCommandTests._registration
    _competition = swiss_fixtures.SwissCommandTests._competition
    _swiss = swiss_fixtures.SwissCommandTests._swiss
    _elimination = swiss_fixtures.SwissCommandTests._elimination
    _revision = swiss_fixtures.SwissCommandTests._revision
    _draw = swiss_fixtures.SwissCommandTests._draw
    _finish = swiss_fixtures.SwissCommandTests._finish
    _generate = swiss_fixtures.SwissCommandTests._generate
    _publish = swiss_fixtures.SwissCommandTests._publish
    preview = EntrantLifecycleTests.preview
    apply = EntrantLifecycleTests.apply
    transition = EntrantLifecycleTests.transition

    def test_fixed_live_removal_restoration_and_later_round_retirement(self):
        draw = self._draw(4)
        match = draw.rounds.get().matches.first()
        self.entrant = match.slots.get(position=1).resolved_entry.entrant
        commands.start_match(
            actor=self.actor, match_id=match.pk, expected_revision=self._revision()
        )
        commands.save_match_progress(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self._revision(),
            side_one_score=1,
            side_two_score=0,
        )
        self.transition()
        self._finish(draw.rounds.get())
        next_round = self._generate()
        self._publish(next_round)
        preview = self.preview(status="ACTIVE")
        self.assertIn(next_round.pk, preview["retired_rounds"])
        self.apply(preview, confirm_resets=True)
        next_round.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(next_round.state, "SUPERSEDED")
        self.assertEqual(
            (match.status, match.side_one_score, match.side_two_score), ("LIVE", 1, 0)
        )

    def test_threshold_pending_removal_and_restore(self):
        draw = self._draw(
            4,
            format="SWISS_THRESHOLD",
            win_target=2,
            loss_limit=2,
            advancement_count=None,
        )
        match = draw.rounds.get().matches.first()
        self.entrant = match.slots.get(position=1).resolved_entry.entrant
        self.transition(status="DISQUALIFIED")
        match.refresh_from_db()
        self.assertEqual(match.outcome, "FORFEIT")
        self.transition(status="ACTIVE")
        match.refresh_from_db()
        self.assertEqual(match.status, "PENDING")

    def test_removal_retires_private_round_without_touching_final_history(self):
        draw = self._draw(4)
        self._finish(draw.rounds.get())
        before = list(Match.objects.filter(round__draw=draw).values())
        private = self._generate()
        self.entrant = draw.entries.first().entrant
        preview = self.preview()
        self.assertIn(private.pk, preview["retired_rounds"])
        self.apply(preview)
        self.assertEqual(
            before,
            list(Match.objects.filter(pk__in=[m["id"] for m in before]).values()),
        )
        private.refresh_from_db()
        self.assertEqual(private.state, "SUPERSEDED")


class LifecycleHandoffTests(TestCase):
    setUp = fixtures.CompetitionCommandTests.setUp
    _registration = fixtures.CompetitionCommandTests._registration
    _chain = handoff_fixtures.HandoffTests._chain
    _finish = handoff_fixtures.HandoffTests._finish
    preview = EntrantLifecycleTests.preview
    apply = EntrantLifecycleTests.apply
    transition = EntrantLifecycleTests.transition

    def test_restore_retains_historical_draws(self):
        source, stage = self._chain(advance_count=2)
        self._finish(source)
        draw = generate_next_stage_draw(
            actor=self.actor,
            stage_id=stage.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            stage_id=stage.pk,
            expected_revision=self.competition.revision,
        )
        self._finish(draw)
        saved = list(Match.objects.filter(round__draw=draw).values())
        self.entrant = draw.entries.first().entrant
        preview = self.preview()
        self.assertEqual(preview["retired_draws"], [draw.pk])
        self.assertEqual(preview["reset_match_ids"], [m["id"] for m in saved])
        with self.assertRaises(ValidationError):
            self.apply(preview)
        self.apply(preview, confirm_resets=True)
        removal = self.competition.changes.latest("revision")
        history = removal.private_data["reset_matches"]
        self.assertEqual([m["match_id"] for m in history], [m["id"] for m in saved])
        self.assertEqual(history[0]["outcome"], "PLAYED")
        self.transition(status="ACTIVE")
        removal.refresh_from_db()
        self.assertEqual(removal.private_data["reset_matches"], history)
        draw.refresh_from_db()
        self.assertEqual(draw.state, "SUPERSEDED")
        self.assertEqual(saved, list(Match.objects.filter(round__draw=draw).values()))
        self.competition.refresh_from_db()
        replacement = generate_next_stage_draw(
            actor=self.actor,
            stage_id=stage.pk,
            expected_revision=self.competition.revision,
        )
        self.assertNotEqual(replacement.pk, draw.pk)
        self.assertEqual(replacement.state, "DRAFT")
