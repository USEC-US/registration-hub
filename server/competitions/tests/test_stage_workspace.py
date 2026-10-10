from unittest.mock import patch

from django.core.exceptions import ValidationError
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

    def _setup_url(self, stage):
        return (
            reverse(
                "admin:competitions_competition_configure_detail",
                args=[self.competition.pk],
            )
            + f"?stage={stage.pk}"
        )

    def _setup_data(self, **overrides):
        return {
            "expected_revision": self.competition.revision,
            "stage_sequence": 1,
            "name": "Groups1",
            "format": "ROUND_ROBIN",
            "default_series_length": 1,
            "series_mode": "BEST_OF",
            "meetings": 1,
            "win_points": 3,
            "draw_points": 1,
            "loss_points": 0,
            "group_count": 3,
            "group_name_1": "Alpha",
            "group_size_1": 3,
            "group_quota_1": 2,
            "group_name_2": "Beta",
            "group_size_2": 2,
            "group_quota_2": 2,
            "group_name_3": "Gamma",
            "group_size_3": 2,
            "group_quota_3": 1,
            **overrides,
        }

    def test_setup_saves_unequal_groups_and_preserves_dropdown_values(self):
        source, _ = self._chain(size=7, publish=False)
        self.client.force_login(self.actor)
        url = self._setup_url(source.stage)
        response = self.client.post(url, self._setup_data())
        self.assertEqual(response.status_code, 302)
        stage = self.competition.stages.get(sequence=1)
        self.assertEqual(stage.format, "ROUND_ROBIN")
        self.assertEqual(
            list(stage.group_plans.values_list("name", "size", "qualifying_places")),
            [("Alpha", 3, 2), ("Beta", 2, 2), ("Gamma", 2, 1)],
        )
        response = self.client.get(url)
        self.assertContains(response, '<select name="group_count"')
        form = response.context_data["form"]
        self.assertEqual(form["group_count"].value(), 3)
        self.assertEqual(form["group_size_2"].value(), 2)
        self.assertEqual(form["group_quota_2"].value(), 2)
        self.assertEqual(form["group_name_3"].value(), "Gamma")
        workspace = self.client.get(workspace_url(self.competition.pk, "setup"))
        self.assertNotContains(workspace, "Advancement rules</a>")
        draw_form = self.client.get(
            reverse(
                "admin:competitions_competition_draw_detail", args=[self.competition.pk]
            )
        )
        self.assertNotIn("group_specs", draw_form.context_data["form"].fields)

    def test_setup_rejects_invalid_group_rules_without_changing_the_plan(self):
        source, _ = self._chain(size=7, publish=False)
        self.client.force_login(self.actor)
        for changes, field in (
            ({"group_quota_2": 3}, "group_quota_2"),
            ({"group_size_1": 2}, "group_count"),
            ({"group_name_3": "Alpha"}, "group_name_3"),
            ({"group_count": 4}, "group_count"),
            ({"group_count": 999999}, "group_count"),
        ):
            with self.subTest(changes=changes):
                response = self.client.post(
                    self._setup_url(source.stage), self._setup_data(**changes)
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context_data["form"].errors)
                source.stage.refresh_from_db()
                self.assertEqual(source.stage.format, "SINGLE_ELIMINATION")
                self.assertFalse(source.stage.group_plans.exists())
                source.refresh_from_db()
                self.assertEqual(source.state, "DRAFT")

    def test_setup_rolls_back_format_and_draw_when_rule_save_fails(self):
        source, _ = self._chain(size=7, publish=False)
        self.client.force_login(self.actor)
        revision = self.competition.revision
        with patch(
            "competitions.admin.set_stage_groups",
            side_effect=ValidationError("Rule save failed"),
        ):
            response = self.client.post(
                self._setup_url(source.stage), self._setup_data()
            )
        self.assertContains(response, "Rule save failed")
        self.competition.refresh_from_db()
        source.stage.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(self.competition.revision, revision)
        self.assertEqual(source.stage.name, "Stage1")
        self.assertEqual(source.stage.format, "SINGLE_ELIMINATION")
        self.assertEqual(source.state, "DRAFT")

    def test_setup_checks_successor_incoming_count(self):
        source, destination = self._chain(size=7, advance_count=4, publish=False)
        self.client.force_login(self.actor)
        response = self.client.post(
            self._setup_url(destination),
            self._setup_data(
                stage_sequence=2, group_count=1, group_size_1=5, group_quota_1=2
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("group_size_1", response.context_data["form"].errors)
        destination.refresh_from_db()
        self.assertEqual(destination.format, "SINGLE_ELIMINATION")

    def test_setup_cannot_change_locked_plan(self):
        source, _ = self._chain(size=7)
        self.client.force_login(self.actor)
        response = self.client.post(self._setup_url(source.stage), self._setup_data())
        self.assertEqual(response.status_code, 200)
        source.stage.refresh_from_db()
        self.assertEqual(source.stage.format, "SINGLE_ELIMINATION")
        self.assertFalse(source.stage.group_plans.exists())

    def test_setup_target_comes_from_stage_context(self):
        source, destination = self._chain(size=7, advance_count=4, publish=False)
        self.client.force_login(self.actor)
        response = self.client.post(
            self._setup_url(destination),
            self._setup_data(
                stage_sequence=1, format="SINGLE_ELIMINATION", advancement_count=3
            ),
        )
        self.assertEqual(response.status_code, 302)
        source.stage.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.stage.advancement_count, 4)
        self.assertEqual(destination.advancement_count, 3)

    def test_format_switch_ignores_outdated_group_sizes(self):
        from competitions.stage_commands import set_stage_advancement

        source, destination = self._chain(
            destination_format="ROUND_ROBIN", size=7, publish=False
        )
        set_stage_advancement(
            actor=self.actor,
            stage_id=source.stage_id,
            expected_revision=self.competition.revision,
            advancement_count=4,
        )
        self.competition.refresh_from_db()
        self.client.force_login(self.actor)
        response = self.client.post(
            self._setup_url(destination),
            self._setup_data(
                stage_sequence=2, format="SINGLE_ELIMINATION", advancement_count=""
            ),
        )
        self.assertEqual(response.status_code, 302)
        destination.refresh_from_db()
        self.assertEqual(destination.format, "SINGLE_ELIMINATION")
        self.assertFalse(destination.group_plans.exists())

    def test_format_switch_ignores_outdated_elimination_quota(self):
        from competitions.commands import select_entrants

        source, _ = self._chain(size=7, publish=False)
        select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=list(
                self.competition.entrants.values_list("registration_id", flat=True)
            )[:4],
        )
        self.competition.refresh_from_db()
        self.client.force_login(self.actor)
        response = self.client.post(
            self._setup_url(source.stage),
            self._setup_data(group_count=1, group_size_1=4, group_quota_1=2),
        )
        self.assertEqual(response.status_code, 302)
        source.stage.refresh_from_db()
        self.assertEqual(source.stage.format, "ROUND_ROBIN")
        self.assertIsNone(source.stage.advancement_count)
        self.assertEqual(source.stage.group_plans.get().size, 4)

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
        url = self._setup_url(source.stage)
        response = self.client.post(
            url,
            self._setup_data(format="SINGLE_ELIMINATION", advancement_count=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("advancement_count", response.context_data["form"].errors)
        final_url = self._setup_url(final)
        response = self.client.post(
            final_url,
            self._setup_data(
                stage_sequence=2, format="SINGLE_ELIMINATION", advancement_count=""
            ),
        )
        self.assertEqual(response.status_code, 302)

    def test_setup_saves_elimination_quota_and_keeps_unchanged_draw(self):
        source, _ = self._chain(size=7, publish=False)
        self.client.force_login(self.actor)
        url = self._setup_url(source.stage)
        response = self.client.post(
            url, self._setup_data(format="SINGLE_ELIMINATION", advancement_count=7)
        )
        self.assertEqual(response.status_code, 302)
        source.refresh_from_db()
        self.assertEqual(source.state, "DRAFT")
        self.competition.refresh_from_db()
        response = self.client.post(
            url, self._setup_data(format="SINGLE_ELIMINATION", advancement_count=3)
        )
        self.assertEqual(response.status_code, 302)
        source.stage.refresh_from_db()
        self.assertEqual(source.stage.advancement_count, 3)
        source.refresh_from_db()
        self.assertEqual(source.state, "SUPERSEDED")

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
