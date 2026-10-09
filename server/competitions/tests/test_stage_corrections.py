from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from competitions.commands import (
    apply_correction,
    preview_correction,
    publish_draw,
    schedule_match,
)
from competitions.models import Match, StageDraw
from competitions.tests.test_handoffs import HandoffTests


class StageCorrectionTests(TestCase):
    setUp = HandoffTests.setUp
    _registration = HandoffTests._registration
    _chain = HandoffTests._chain
    _finish = HandoffTests._finish

    def _played_destination(self):
        from competitions.handoff_commands import generate_next_stage_draw

        source, destination = self._chain()
        self._finish(source)
        draw = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self._finish(draw)
        return source, draw

    def test_unchanged_valid_qualifiers_preserve_played_successor(self):
        source, destination = self._played_destination()
        match = Match.objects.filter(round__draw=source).order_by("-pk").first()
        saved = list(
            Match.objects.filter(round__draw=destination).values_list(
                "pk", "side_one_score", "side_two_score"
            )
        )
        before = destination.source_fingerprint
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            outcome="FORFEIT",
            winner_position=2,
        )
        self.assertEqual(
            preview["handoff_impact"]["retained_draw_ids"], [destination.pk]
        )
        apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Correct terminal result",
        )
        destination.refresh_from_db()
        self.assertEqual(destination.state, "PUBLISHED")
        self.assertNotEqual(destination.source_fingerprint, before)
        self.assertEqual(
            list(
                Match.objects.filter(round__draw=destination).values_list(
                    "pk", "side_one_score", "side_two_score"
                )
            ),
            saved,
        )

    def test_unchanged_set_but_reopened_source_retires_suffix_and_preserves_scores(
        self,
    ):
        source, destination = self._played_destination()
        match = Match.objects.filter(round__draw=source).order_by("pk").first()
        played = Match.objects.filter(round__draw=destination, outcome="PLAYED").first()
        scores = (played.side_one_score, played.side_two_score)
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=1,
        )
        self.assertEqual(
            preview["handoff_impact"]["superseded_draw_ids"], [destination.pk]
        )
        self.assertTrue(preview["handoff_impact"]["reset_matches"])
        apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Replay changed path",
        )
        destination.refresh_from_db()
        played.refresh_from_db()
        self.assertEqual(destination.state, StageDraw.State.SUPERSEDED)
        self.assertEqual((played.side_one_score, played.side_two_score), scores)
        destination.stage.refresh_from_db()
        self.assertEqual(destination.stage.status, "AWAITING")
        self.assertIsNotNone(destination.stage.published_at)
        self.competition.refresh_from_db()
        with self.assertRaises(ValidationError):
            schedule_match(
                actor=self.actor,
                match_id=played.pk,
                expected_revision=self.competition.revision,
                scheduled_at=None,
            )
        with self.assertRaises(ValidationError):
            preview_correction(
                actor=self.actor,
                match_id=played.pk,
                expected_revision=self.competition.revision,
                outcome="PLAYED",
                side_one_score=1,
                side_two_score=0,
            )

    def test_suffix_retirement_rolls_back_with_history_failure(self):
        source, destination = self._played_destination()
        match = Match.objects.filter(round__draw=source).first()
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=1,
        )
        with (
            patch(
                "competitions.commands._record_change",
                side_effect=RuntimeError("history failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            apply_correction(
                actor=self.actor, token=preview["token"], internal_reason="Correction"
            )
        destination.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(destination.state, "PUBLISHED")
        self.assertEqual(match.side_one_score, 1)
