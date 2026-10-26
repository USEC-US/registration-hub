from django.test import TestCase

from competitions.commands import apply_correction, preview_correction
from competitions.models import Match
from competitions.tests import test_stage_corrections as fixtures


class StageApiTests(TestCase):
    setUp = fixtures.StageCorrectionTests.setUp
    _registration = fixtures.StageCorrectionTests._registration
    _chain = fixtures.StageCorrectionTests._chain
    _finish = fixtures.StageCorrectionTests._finish
    _played_destination = fixtures.StageCorrectionTests._played_destination

    def test_retired_public_stage_match_and_private_replacement_visibility(self):
        from competitions.handoff_commands import generate_next_stage_draw

        source, destination = self._played_destination()
        old_match = Match.objects.filter(
            round__draw=destination, outcome="PLAYED"
        ).first()
        match = Match.objects.filter(round__draw=source).first()
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=1,
        )
        apply_correction(
            actor=self.actor, token=preview["token"], internal_reason="PRIVATE-reason"
        )
        self._finish(source)
        replacement = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.stage_id,
            expected_revision=self.competition.revision,
        )
        response = self.client.get(f"/api/competition-stages/{destination.stage_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["draw_state"], "AWAITING_REPLACEMENT")
        self.assertEqual(response.data["lifecycle_state"], "RETIRED")
        self.assertEqual(
            {e["id"] for e in response.data["entries"]},
            set(destination.entries.values_list("pk", flat=True)),
        )
        self.assertTrue(response.data["rounds"])
        self.assertTrue(
            all(m["historical"] for r in response.data["rounds"] for m in r["matches"])
        )
        self.assertIsNone(response.data["swiss_rules"])
        self.assertEqual(response.data["swiss_standings"], [])
        detail = self.client.get(f"/api/competition-matches/{old_match.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data["historical"])
        self.assertEqual(
            (detail.data["side_one_score"], detail.data["side_two_score"]), (1, 0)
        )
        private = Match.objects.filter(round__draw=replacement).first()
        self.assertEqual(
            self.client.get(f"/api/competition-matches/{private.pk}/").status_code, 404
        )
        overview = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        )
        self.assertEqual(len(overview.data["stages"]), 2)
        rendered = overview.rendered_content.decode()
        for key in (
            "source_draw",
            "source_fingerprint",
            "actor",
            "internal_reason",
            "registration_id",
            "group_plans",
        ):
            self.assertNotIn(key, rendered)
        changes = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/changes/"
        )
        correction = next(
            c for c in changes.data["results"] if c["kind"] == "result_corrected"
        )
        self.assertEqual(
            correction["handoff_impact"]["retired_draws"],
            [{"stage_id": destination.stage_id, "draw_id": destination.pk}],
        )
        self.assertNotIn("PRIVATE-reason", changes.rendered_content.decode())

    def test_public_qualification_has_only_the_published_source_field(self):
        source, destination = self._chain()
        response = self.client.get(f"/api/competition-stages/{source.stage_id}/")
        self.assertEqual(response.data["draw_state"], "PUBLISHED")
        self.assertEqual(response.data["qualification"]["advance_count"], 4)
        self.assertEqual(response.data["qualification"]["state"], "PROVISIONAL")
        self.assertEqual(
            self.client.get(f"/api/competition-stages/{destination.pk}/").status_code,
            404,
        )
