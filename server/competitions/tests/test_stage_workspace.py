from django.test import TestCase, override_settings
from django.urls import reverse

from competitions.admin_workspace import workspace_url
from competitions.tests import test_handoffs as fixtures


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class StageWorkspaceTests(TestCase):
    setUp = fixtures.HandoffTests.setUp
    _registration = fixtures.HandoffTests._registration
    _chain = fixtures.HandoffTests._chain
    _finish = fixtures.HandoffTests._finish

    def test_stage_context_survives_tabs_and_return_links(self):
        source, destination = self._chain()
        self.client.force_login(self.actor)
        base = reverse(
            "admin:competitions_competition_change", args=[self.competition.pk]
        )
        self.assertEqual(
            workspace_url(self.competition.pk, "standings", stage_id=destination.pk),
            f"{base}?tab=standings&stage={destination.pk}",
        )
        response = self.client.get(f"{base}?stage={destination.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["stage"].pk, destination.pk)
        self.assertContains(response, "Waiting for previous stage")
        self.assertContains(response, f"?tab=setup&amp;stage={destination.pk}")
        self.assertEqual(self.client.get(f"{base}?stage=999999").status_code, 404)

    def test_publication_explains_lock_and_forged_early_handoff_is_rejected(self):
        source, destination = self._chain()
        self.client.force_login(self.actor)
        url = reverse(
            "admin:competitions_competition_publish_detail", args=[self.competition.pk]
        )
        response = self.client.get(f"{url}?stage={destination.pk}")
        self.assertContains(response, "whole stage plan")
        generate = reverse(
            "admin:competitions_stage_generate",
            args=[self.competition.pk, destination.pk],
        )
        response = self.client.post(
            generate, {"expected_revision": self.competition.revision, "regenerate": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(destination.draws.exists())
        self._finish(source)
        response = self.client.post(
            generate, {"expected_revision": self.competition.revision}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            workspace_url(self.competition.pk, "bracket", stage_id=destination.pk),
        )

    def test_nonfinal_elimination_rules_require_a_quota(self):
        source, final = self._chain(publish=False)
        self.client.force_login(self.actor)
        url = reverse(
            "admin:competitions_stage_rules",
            args=[self.competition.pk, source.stage_id],
        )
        response = self.client.post(
            url,
            {"expected_revision": self.competition.revision, "advancement_count": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("advancement_count", response.context_data["form"].errors)
        final_url = reverse(
            "admin:competitions_stage_rules", args=[self.competition.pk, final.pk]
        )
        response = self.client.post(
            final_url,
            {"expected_revision": self.competition.revision, "advancement_count": ""},
        )
        self.assertEqual(response.status_code, 302)

    def test_round_action_preserves_destination_stage(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.commands import publish_draw

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
        self.competition.refresh_from_db()
        self.client.force_login(self.actor)
        round_ = draw.rounds.first()
        action = reverse("admin:competitions_round_series_detail", args=[round_.pk])
        response = self.client.get(action)
        expected = workspace_url(
            self.competition.pk, "bracket", stage_id=destination.pk
        )
        self.assertContains(response, expected.replace("&", "&amp;"))
        response = self.client.post(
            action, {"expected_revision": self.competition.revision, "series_length": 3}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, expected)

    def test_replacement_private_preview_offers_regeneration(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.commands import publish_draw

        source, destination = self._chain(source_format="ROUND_ROBIN")
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
        self.competition.refresh_from_db()
        # A published identity with a replacement draft is the state after retirement/replay.
        draw.state = "SUPERSEDED"
        draw.save(update_fields=("state",))
        replacement = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.client.force_login(self.actor)
        url = workspace_url(self.competition.pk, "setup", stage_id=destination.pk)
        response = self.client.get(url)
        regenerate = reverse(
            "admin:competitions_stage_generate",
            args=[self.competition.pk, destination.pk],
        )
        self.assertContains(response, regenerate)
        self.assertEqual(replacement.state, "DRAFT")

    def test_future_stage_without_published_source_shows_waiting_state(self):
        source, destination = self._chain(publish=False)
        self.client.force_login(self.actor)
        response = self.client.get(
            workspace_url(self.competition.pk, "setup", stage_id=destination.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waiting for previous stage")
        self.assertEqual(response.context_data["stage"].pk, destination.pk)

    def test_third_stage_waits_when_predecessor_is_unpublished_or_retired(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.commands import (
            publish_draw,
            preview_correction,
            apply_correction,
        )
        from competitions.models import Match

        source, destination = self._chain(formats=("SINGLE_ELIMINATION",) * 3)
        third = self.competition.stages.get(sequence=3)
        self.client.force_login(self.actor)
        url = workspace_url(self.competition.pk, "setup", stage_id=third.pk)
        self.assertEqual(self.client.get(url).status_code, 200)
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
        self.competition.refresh_from_db()
        match = Match.objects.filter(round__draw=source).order_by("pk").first()
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=1,
        )
        apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Replay changed path",
        )
        draw.refresh_from_db()
        self.assertEqual(draw.state, "SUPERSEDED")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waiting for previous stage")
