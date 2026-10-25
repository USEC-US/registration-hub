from django.core import signing
from django.core.exceptions import ValidationError
from django.test import TestCase

from competitions import commands, lifecycle_commands as lifecycle
from competitions.models import Match, StageDraw
from competitions.tests import test_handoffs as fixtures
from competitions.tests import test_swiss_commands as swiss_fixtures


class CompetitionLifecycleTests(TestCase):
    setUp = fixtures.HandoffTests.setUp
    _registration = fixtures.HandoffTests._registration
    _chain = fixtures.HandoffTests._chain
    _finish = fixtures.HandoffTests._finish

    def preview(self, award=False):
        self.competition.refresh_from_db()
        return lifecycle.preview_competition_end(
            actor=self.actor,
            stage_id=self.source.stage_id,
            expected_revision=self.competition.revision,
            award_sole_survivor=award,
        )

    def end(self, preview=None, **kwargs):
        return lifecycle.apply_competition_end(
            actor=self.actor,
            token=(preview or self.preview())["token"],
            internal_reason="Cannot fill locked field",
            **kwargs,
        )

    def remove(self, entrant):
        self.competition.refresh_from_db()
        preview = lifecycle.preview_entrant_transition(
            actor=self.actor,
            entrant_id=entrant.pk,
            expected_revision=self.competition.revision,
            status="WITHDRAWN",
        )
        lifecycle.apply_entrant_transition(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Unavailable",
            confirm_live_forfeits=True,
            confirm_resets=True,
        )

    def test_viable_unfinished_and_completed_continuation_cannot_end(self):
        self.source, _ = self._chain()
        with self.assertRaises(ValidationError):
            self.preview()
        self._finish(self.source)
        with self.assertRaises(ValidationError):
            self.preview()

    def test_zero_one_multiple_candidates_award_and_atomic_history(self):
        self.source, _ = self._chain()
        self._finish(self.source)
        entrants = list(self.source.entries.select_related("entrant").order_by("seed"))
        self.remove(entrants[0].entrant)
        preview = self.preview()
        with self.assertRaises(ValidationError):
            self.preview(True)
        self.remove(entrants[1].entrant)
        self.remove(entrants[2].entrant)
        preview = self.preview(True)
        before = list(Match.objects.values())
        revision = self.competition.revision
        self.assertEqual(
            lifecycle.review_lifecycle_preview(
                actor=self.actor, token=preview["token"]
            ),
            preview,
        )
        self.end(preview)
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.ended_champion_id, entrants[3].entrant_id)
        self.assertEqual(self.competition.revision, revision + 1)
        self.assertEqual(before, list(Match.objects.values()))
        self.assertEqual(
            self.competition.changes.latest("revision").kind, "competition_ended"
        )
        with self.assertRaises(ValidationError):
            self.end(preview)

    def test_reopen_requires_confirmation_and_keeps_retired_draws(self):
        from competitions.handoff_commands import generate_next_stage_draw

        self.source, destination = self._chain()
        self._finish(self.source)
        suffix = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        # Registration eligibility can change independently of competition commands.
        entry = self.source.entries.first()
        entry.entrant.registration.status = "REJECTED"
        entry.entrant.registration.save(update_fields=["status"])
        preview = self.preview()
        self.assertEqual(preview["retired_draws"], [suffix.pk])
        self.end(preview)
        self.competition.refresh_from_db()
        reopen = lifecycle.preview_competition_reopen(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )
        before = list(Match.objects.values())
        with self.assertRaises(ValidationError):
            lifecycle.apply_competition_reopen(
                actor=self.actor, token=reopen["token"], internal_reason="Recover"
            )
        for consent in (1, 0, "true", None):
            with self.subTest(consent=consent), self.assertRaises(ValidationError):
                lifecycle.apply_competition_reopen(
                    actor=self.actor,
                    token=reopen["token"],
                    internal_reason="Recover",
                    confirm_resets=consent,
                )
        self.assertEqual(
            lifecycle.review_lifecycle_preview(actor=self.actor, token=reopen["token"]),
            reopen,
        )
        lifecycle.apply_competition_reopen(
            actor=self.actor,
            token=reopen["token"],
            internal_reason="Recover",
            confirm_resets=True,
        )
        with self.assertRaises(ValidationError):
            lifecycle.apply_competition_reopen(
                actor=self.actor,
                token=reopen["token"],
                internal_reason="Repeat",
                confirm_resets=True,
            )
        suffix.refresh_from_db()
        self.assertEqual(suffix.state, StageDraw.State.SUPERSEDED)
        self.assertEqual(before, list(Match.objects.values()))
        with self.assertRaises(ValidationError):
            generate_next_stage_draw(
                actor=self.actor,
                stage_id=destination.pk,
                expected_revision=self.competition.revision + 1,
            )
        entry.entrant.registration.status = "APPROVED"
        entry.entrant.registration.save(update_fields=["status"])
        self.competition.refresh_from_db()
        replacement = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.assertNotEqual(replacement.pk, suffix.pk)
        self.assertEqual(replacement.state, "DRAFT")

    def test_ended_match_commands_are_denied_without_changes(self):
        self.source, _ = self._chain()
        match = Match.objects.filter(round__draw=self.source).first()
        for entry in self.source.entries.all():
            self.remove(entry.entrant)
        self.end()
        self.competition.refresh_from_db()
        before = list(Match.objects.values())
        history = list(self.competition.changes.values())
        common = dict(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
        )
        calls = [
            lambda: commands.start_match(**common),
            lambda: commands.schedule_match(**common, scheduled_at=None),
            lambda: commands.save_match_progress(
                **common, side_one_score=0, side_two_score=0
            ),
            lambda: commands.finalize_match(**common, outcome="DOUBLE_FORFEIT"),
            lambda: commands.set_match_series_length(**common, series_length=3),
        ]
        for call in calls:
            with (
                self.subTest(call=call),
                self.assertRaisesRegex(ValidationError, "Reopen"),
            ):
                call()
            self.assertEqual(before, list(Match.objects.values()))
            self.assertEqual(history, list(self.competition.changes.values()))

    def test_all_mutation_families_reject_ended_state(self):
        from competitions import (
            stage_commands,
            swiss_commands,
            round_robin_commands,
            qualification,
        )
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.models import Stage, Round, TieResolution, CompetitionEntrant

        self.source, destination = self._chain()
        self._finish(self.source)
        match = Match.objects.filter(round__draw=self.source, outcome="PLAYED").first()
        for entry in self.source.entries.all():
            self.remove(entry.entrant)
        self.end()
        self.competition.refresh_from_db()
        base = dict(actor=self.actor, expected_revision=self.competition.revision)
        comp = dict(base, competition_id=self.competition.pk)
        stage = dict(base, stage_id=self.source.stage_id)
        tied = signing.dumps(
            dict(competition_id=self.competition.pk, method="MANUAL"),
            salt=qualification.TIE_SALT,
        )
        correction = commands.preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=1,
            side_two_score=0,
        )
        entrant = self.source.entries.first().entrant
        transition = signing.dumps(
            dict(
                competition_id=self.competition.pk,
                revision=self.competition.revision,
                entrant_id=entrant.pk,
                kind="entrant_status_changed",
                after={"status": "DISQUALIFIED"},
            ),
            salt=lifecycle.LIFECYCLE_SALT,
        )
        calls = [
            (
                commands.configure_elimination,
                dict(
                    comp,
                    format="SINGLE_ELIMINATION",
                    name="Changed",
                    default_series_length=1,
                ),
            ),
            (
                round_robin_commands.configure_round_robin,
                dict(
                    comp,
                    name="Changed",
                    meetings=1,
                    series_mode="BEST_OF",
                    default_series_length=1,
                    win_points=3,
                    draw_points=1,
                    loss_points=0,
                ),
            ),
            (
                swiss_commands.configure_swiss,
                dict(
                    comp,
                    name="Changed",
                    format="SWISS_FIXED",
                    series_mode="BEST_OF",
                    default_series_length=1,
                    round_count=2,
                    win_target=None,
                    loss_limit=None,
                    advancement_count=2,
                    win_points=3,
                    draw_points=1,
                    loss_points=0,
                    tiebreaks=[],
                ),
            ),
            (
                commands.select_entrants,
                dict(comp, registration_ids=[r.pk for r in self.registrations]),
            ),
            (commands.save_elimination_draw, comp),
            (
                round_robin_commands.save_round_robin_draw,
                dict(comp, group_specs=[("A", 2)], ordered_entrant_ids=[]),
            ),
            (swiss_commands.save_swiss_draw, comp),
            (commands.publish_draw, comp),
            (generate_next_stage_draw, dict(base, stage_id=destination.pk)),
            (swiss_commands.generate_swiss_round, stage),
            (swiss_commands.publish_swiss_round, dict(base, round_id=match.round_id)),
            (stage_commands.set_stage_advancement, dict(stage, advancement_count=2)),
            (stage_commands.set_stage_groups, dict(stage, group_specs=[("A", 4, 2)])),
            (
                stage_commands.reorder_stages,
                dict(comp, stage_ids=[self.source.stage_id, destination.pk]),
            ),
            (stage_commands.remove_stage, stage),
            (
                commands.set_round_series_length,
                dict(base, round_id=match.round_id, series_length=1),
            ),
            (
                qualification.confirm_qualification_tie,
                dict(actor=self.actor, token=tied, internal_reason="Decision"),
            ),
            (
                round_robin_commands.confirm_group_tie,
                dict(actor=self.actor, token=tied, internal_reason="Decision"),
            ),
            (
                commands.apply_correction,
                dict(
                    actor=self.actor,
                    token=correction["token"],
                    internal_reason="Correction",
                ),
            ),
            (
                lifecycle.apply_entrant_transition,
                dict(actor=self.actor, token=transition, internal_reason="Change"),
            ),
        ]
        models = [Match, StageDraw, Stage, Round, TieResolution, CompetitionEntrant]
        before = [list(model.objects.values()) for model in models]
        history = list(self.competition.changes.values())
        for command, kwargs in calls:
            with (
                self.subTest(command=command.__name__),
                self.assertRaisesRegex(ValidationError, "Reopen"),
            ):
                command(**kwargs)
            self.assertEqual(before, [list(model.objects.values()) for model in models])
            self.assertEqual(history, list(self.competition.changes.values()))

    def test_published_suffix_requires_permission_and_consent_preserves_history(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from django.core.exceptions import PermissionDenied
        from unittest.mock import patch

        self.source, destination = self._chain()
        self._finish(self.source)
        suffix = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_id=destination.pk,
        )
        self._finish(suffix)
        entry = self.source.entries.first()
        entry.entrant.registration.status = "REJECTED"
        entry.entrant.registration.save(update_fields=["status"])
        preview = self.preview()
        before = list(Match.objects.values())
        with self.assertRaises(ValidationError):
            self.end(preview)
        from django.contrib.auth.models import Group

        self.actor.groups.add(Group.objects.get_or_create(name="Organizers")[0])
        self.actor.is_superuser = False
        with patch.object(
            self.actor,
            "has_perm",
            side_effect=lambda perm: perm != "competitions.change_match",
        ):
            with self.assertRaises(PermissionDenied):
                self.end(preview, confirm_resets=True)
        self.actor.is_superuser = True
        self.end(preview, confirm_resets=True)
        self.assertEqual(before, list(Match.objects.values()))
        suffix.refresh_from_db()
        self.assertEqual(suffix.state, "SUPERSEDED")
        self.assertIsNotNone(suffix.published_at)
        event = self.competition.changes.latest("revision")
        self.assertEqual(event.public_data["retired_draws"], [suffix.pk])
        self.assertTrue(event.public_data["reset_matches"])

    def test_live_source_freezes_without_fictitious_results(self):
        self.source, _ = self._chain(advance_count=4)
        matches = list(
            Match.objects.filter(round__draw=self.source, round__number=1).order_by(
                "pk"
            )
        )
        commands.start_match(
            actor=self.actor,
            match_id=matches[0].pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.save_match_progress(
            actor=self.actor,
            match_id=matches[0].pk,
            expected_revision=self.competition.revision,
            side_one_score=0,
            side_two_score=0,
        )
        unavailable = matches[1].slots.first().resolved_entry.entrant
        self.remove(unavailable)
        preview = self.preview()
        self.assertIn(matches[0].pk, preview["frozen_match_ids"])
        before = list(Match.objects.values())
        with self.assertRaises(ValidationError):
            self.end(preview)
        self.end(preview, confirm_resets=True)
        self.assertEqual(before, list(Match.objects.values()))
        self.competition.refresh_from_db()
        reopen = lifecycle.preview_competition_reopen(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )
        lifecycle.apply_competition_reopen(
            actor=self.actor,
            token=reopen["token"],
            internal_reason="Recover",
            confirm_resets=True,
        )
        self.assertEqual(before, list(Match.objects.values()))

    def test_private_suffix_stays_private_and_reopen_permissions(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from django.core.exceptions import PermissionDenied
        from unittest.mock import patch

        self.source, destination = self._chain()
        self._finish(self.source)
        suffix = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        entry = self.source.entries.first()
        entry.entrant.registration.status = "REJECTED"
        entry.entrant.registration.save(update_fields=["status"])
        from django.contrib.auth.models import Group

        self.actor.groups.add(Group.objects.get_or_create(name="Organizers")[0])
        self.actor.is_superuser = False
        with patch.object(
            self.actor,
            "has_perm",
            side_effect=lambda perm: perm != "competitions.change_match",
        ):
            self.end()
            self.competition.refresh_from_db()
            with self.assertRaises(PermissionDenied):
                lifecycle.preview_competition_reopen(
                    actor=self.actor,
                    competition_id=self.competition.pk,
                    expected_revision=self.competition.revision,
                )
        event = self.competition.changes.latest("revision")
        self.assertEqual(event.public_data["retired_draws"], [])
        self.assertEqual(event.public_data["retired_rounds"], [])
        self.assertIn(suffix.pk, event.private_data["retired_draws"])

    def test_invalid_tokens_cross_scope_and_stale_eligibility(self):
        self.source, _ = self._chain()
        self._finish(self.source)
        self.remove(self.source.entries.first().entrant)
        preview = self.preview()
        for token in (None, {}, "bad", preview["token"] + "tampered"):
            with self.subTest(token=token), self.assertRaises(ValidationError):
                lifecycle.apply_competition_end(
                    actor=self.actor, token=token, internal_reason="Reason"
                )
        payload = signing.loads(preview["token"], salt=lifecycle.LIFECYCLE_SALT)
        for field, value in (
            ("stage_id", 999999),
            ("competition_id", 999999),
            ("after", {"champion_id": 999999}),
        ):
            token = signing.dumps(
                {**payload, field: value}, salt=lifecycle.LIFECYCLE_SALT
            )
            with self.subTest(field=field), self.assertRaises(ValidationError):
                lifecycle.apply_competition_end(
                    actor=self.actor, token=token, internal_reason="Reason"
                )
        with self.assertRaises(ValidationError):
            lifecycle.apply_entrant_transition(
                actor=self.actor,
                token=preview["token"],
                internal_reason="Wrong operation",
            )
        with self.assertRaises(ValidationError):
            lifecycle.apply_competition_reopen(
                actor=self.actor,
                token=preview["token"],
                internal_reason="Wrong operation",
                confirm_resets=True,
            )
        entrant = self.source.entries.last().entrant
        entrant.registration.status = "REJECTED"
        entrant.registration.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self.end(preview)

    def test_viable_cutoff_tie_cannot_be_skipped(self):
        self.source, _ = self._chain(source_format="ROUND_ROBIN", advance_count=2)
        # Four identical records leave a real qualification decision unresolved.
        for match in Match.objects.filter(round__draw=self.source).order_by("pk"):
            self.competition.refresh_from_db()
            commands.finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self.competition.revision,
                outcome="DOUBLE_FORFEIT",
            )
        with self.assertRaises(ValidationError):
            self.preview()

    def test_normal_final_champion_is_not_an_exceptional_ending(self):
        from competitions.handoff_commands import generate_next_stage_draw

        self.source, destination = self._chain()
        self._finish(self.source)
        self.source = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_id=destination.pk,
        )
        self._finish(self.source)
        with self.assertRaises(ValidationError):
            self.preview()

    def test_no_champion_when_only_remaining_entrant_was_not_a_qualifier(self):
        self.source, _ = self._chain(advance_count=2)
        self._finish(self.source)
        from competitions.qualification import stage_qualification

        earned = stage_qualification(self.source)["qualifier_entry_ids"]
        for entry in self.source.entries.all():
            if entry.pk in earned:
                self.remove(entry.entrant)
        with self.assertRaises(ValidationError):
            self.preview(True)
        self.end()
        self.competition.refresh_from_db()
        self.assertIsNone(self.competition.ended_champion_id)

    def test_unfinished_round_robin_group_cannot_fill_its_locked_quota(self):
        from competitions.stage_commands import set_stage_groups
        from competitions.round_robin_commands import save_round_robin_draw

        self.source, _ = self._chain(
            source_format="ROUND_ROBIN", advance_count=2, publish=False
        )
        set_stage_groups(
            actor=self.actor,
            stage_id=self.source.stage_id,
            expected_revision=self.competition.revision,
            group_specs=[("A", 2, 1), ("B", 2, 1)],
        )
        self.competition.refresh_from_db()
        ids = list(self.competition.entrants.values_list("pk", flat=True))
        self.source = save_round_robin_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            group_specs=[("A", 1), ("B", 1)],
            ordered_entrant_ids=ids,
            memberships=[ids[:2], ids[2:]],
        )
        self.competition.refresh_from_db()
        commands.publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )
        for entry in self.source.groups.get(name="A").entries.all():
            self.remove(entry.entrant)
        preview = self.preview()
        self.assertTrue(preview["frozen_match_ids"])
        self.end(preview)

    def test_repeated_end_reopen_cycles_do_not_repeat_retirement(self):
        self.source, _ = self._chain()
        self._finish(self.source)
        self.remove(self.source.entries.first().entrant)
        before = list(Match.objects.values())
        self.competition.refresh_from_db()
        revision = self.competition.revision
        for _ in range(2):
            preview = self.preview()
            for consent in (1, "true", None):
                with self.subTest(consent=consent), self.assertRaises(ValidationError):
                    self.end(preview, confirm_resets=consent)
            self.end(preview)
            self.competition.refresh_from_db()
            reopen = lifecycle.preview_competition_reopen(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
            )
            lifecycle.apply_competition_reopen(
                actor=self.actor,
                token=reopen["token"],
                internal_reason="Recover",
                confirm_resets=True,
            )
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.revision, revision + 4)
        self.assertEqual(before, list(Match.objects.values()))
        self.assertEqual(
            self.competition.changes.filter(kind="competition_ended").count(), 2
        )
        self.assertEqual(
            self.competition.changes.filter(kind="competition_reopened").count(), 2
        )

    def test_double_elimination_blocked_field_ends_without_rewriting_results(self):
        self.source, _ = self._chain(source_format="DOUBLE_ELIMINATION")
        self._finish(self.source)
        self.remove(self.source.entries.first().entrant)
        before = list(Match.objects.values())
        self.end()
        self.assertEqual(before, list(Match.objects.values()))

    def test_unavailable_cutoff_contender_never_yields_an_inferred_champion(self):
        self.source, _ = self._chain(source_format="ROUND_ROBIN", advance_count=2)
        for match in Match.objects.filter(round__draw=self.source).order_by("pk"):
            self.competition.refresh_from_db()
            commands.finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self.competition.revision,
                outcome="DOUBLE_FORFEIT",
            )
        for entry in list(self.source.entries.all())[:3]:
            self.remove(entry.entrant)
        with self.assertRaises(ValidationError):
            self.preview(True)
        self.end()

    def test_failed_history_write_rolls_back_outcome_and_retirement(self):
        from unittest.mock import patch
        from competitions.handoff_commands import generate_next_stage_draw

        self.source, destination = self._chain()
        self._finish(self.source)
        suffix = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        registration = self.source.entries.first().entrant.registration
        registration.status = "REJECTED"
        registration.save(update_fields=["status"])
        preview = self.preview()
        revision = self.competition.revision
        with patch.object(
            lifecycle,
            "_record_change",
            side_effect=RuntimeError("Simulated storage failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.end(preview)
        self.competition.refresh_from_db()
        suffix.refresh_from_db()
        self.assertIsNone(self.competition.ended_at)
        self.assertEqual(self.competition.revision, revision)
        self.assertEqual(suffix.state, "DRAFT")
        self.assertFalse(
            self.competition.changes.filter(kind="competition_ended").exists()
        )


class SwissEndingTests(TestCase):
    setUp = swiss_fixtures.SwissCommandTests.setUp
    _registration = swiss_fixtures.SwissCommandTests._registration
    _competition = swiss_fixtures.SwissCommandTests._competition
    _swiss = swiss_fixtures.SwissCommandTests._swiss
    _elimination = swiss_fixtures.SwissCommandTests._elimination
    _revision = swiss_fixtures.SwissCommandTests._revision
    _draw = swiss_fixtures.SwissCommandTests._draw
    remove = CompetitionLifecycleTests.remove
    preview = CompetitionLifecycleTests.preview
    end = CompetitionLifecycleTests.end

    def test_fixed_swiss_impossible_quota_and_sole_survivor(self):
        self.source = self._draw(4)
        entries = list(self.source.entries.order_by("seed"))
        for entry in entries[1:]:
            self.remove(entry.entrant)
        preview = self.preview(True)
        self.end(preview)
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.ended_champion_id, entries[0].entrant_id)

    def test_threshold_swiss_zero_eligible_candidates(self):
        self.source = self._draw(
            4,
            format="SWISS_THRESHOLD",
            advancement_count=None,
            round_count=None,
            win_target=2,
            loss_limit=2,
        )
        for entry in self.source.entries.all():
            self.remove(entry.entrant)
        with self.assertRaises(ValidationError):
            self.preview(True)
        self.end()
        self.competition.refresh_from_db()
        self.assertIsNone(self.competition.ended_champion_id)

    def test_fixed_swiss_viable_rounds_cannot_be_skipped(self):
        self.source = self._draw(4)
        with self.assertRaises(ValidationError):
            self.preview()

    def test_threshold_sole_survivor_award_belongs_to_competition(self):
        self.source = self._draw(
            4,
            format="SWISS_THRESHOLD",
            advancement_count=None,
            round_count=None,
            win_target=1,
            loss_limit=1,
        )
        entries = list(self.source.entries.order_by("seed"))
        for entry in entries[1:]:
            self.remove(entry.entrant)
        self.end(self.preview(True))
        self.competition.refresh_from_db()
        self.stage.refresh_from_db()
        self.assertEqual(self.competition.ended_champion_id, entries[0].entrant_id)
        self.assertIsNone(self.stage.champion_id)
