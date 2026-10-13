from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.tests.factories import create_account
from competitions import commands, swiss_commands
from competitions.admin_workspace import correction_display, workspace_url
from competitions.tests import test_swiss_commands as fixtures
from competitions.tests import test_swiss_handoffs as handoff_fixtures


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class SwissWorkspaceTests(TestCase):
    setUp = fixtures.SwissCommandTests.setUp
    _registration = fixtures.SwissCommandTests._registration
    _competition = fixtures.SwissCommandTests._competition
    _swiss = fixtures.SwissCommandTests._swiss
    _elimination = fixtures.SwissCommandTests._elimination
    _draw = fixtures.SwissCommandTests._draw
    _revision = fixtures.SwissCommandTests._revision
    _finish = fixtures.SwissCommandTests._finish
    _generate = fixtures.SwissCommandTests._generate
    _publish = fixtures.SwissCommandTests._publish
    _rematch_dead_end = fixtures.SwissCommandTests._rematch_dead_end

    def _url(self, action, stage=None):
        return reverse(
            f"admin:competitions_swiss_{action}",
            args=[self.competition.pk, (stage or self.stage).pk],
        )

    def _setup_url(self, stage=None):
        return (
            reverse(
                "admin:competitions_competition_configure_detail",
                args=[self.competition.pk],
            )
            + f"?stage={(stage or self.stage).pk}"
        )

    def _data(self, **overrides):
        return (
            dict(
                expected_revision=self._revision(),
                name="Swiss",
                format="SWISS_FIXED",
                default_series_length=3,
                series_mode="BEST_OF",
                round_policy="AUTOMATIC",
                round_count="",
                advancement_count=2,
                win_points=3,
                draw_points=1,
                loss_points=0,
                tiebreak_1="OPPONENT_POINTS",
                tiebreak_2="GAME_DIFFERENCE",
                tiebreak_3="GAMES_WON",
            )
            | overrides
        )

    def test_known_recommendation_and_custom_rounds_survive_edit(self):
        self._draw(count=8, publish=False, round_count=5)
        self.client.force_login(self.actor)
        response = self.client.get(self._setup_url())
        form = response.context_data["form"]
        self.assertEqual(form["round_policy"].value(), "CUSTOM")
        self.assertEqual(form["round_count"].value(), 5)
        self.assertContains(response, "Recommended rounds: 3")
        response = self.client.post(
            self._setup_url(), self._data(round_policy="CUSTOM", round_count=4)
        )
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        self.stage.refresh_from_db()
        self.assertEqual(self.stage.swiss_round_count, 4)
        self.assertEqual(
            response.url, workspace_url(self.competition.pk, stage_id=self.stage.pk)
        )

    def test_unknown_later_field_formula_and_automatic_rr_sizes(self):
        self._competition(8)
        self.stage = self._swiss(
            format="SWISS_THRESHOLD", win_target=2, loss_limit=2, advancement_count=None
        )
        later = self._swiss(2, advancement_count=2)
        self._elimination(3)
        self.client.force_login(self.actor)
        response = self.client.get(self._setup_url(later))
        self.assertContains(response, "ceil(log2(actual N))")
        self.assertIsNone(response.context_data["form"].incoming_count)
        data = self._data()
        data.update(
            format="ROUND_ROBIN",
            tiebreak_1="HEAD_TO_HEAD",
            group_count=2,
            group_size_policy="AUTOMATIC",
            group_name_1="A",
            group_quota_1=2,
            group_name_2="B",
            group_quota_2=1,
        )
        response = self.client.post(self._setup_url(later), data)
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        later.refresh_from_db()
        self.assertEqual(
            list(later.group_plans.values_list("size", "qualifying_places")),
            [(None, 2), (None, 1)],
        )
        response = self.client.get(self._setup_url(later))
        self.assertEqual(
            response.context_data["form"]["group_size_policy"].value(), "AUTOMATIC"
        )

    def test_saved_exact_rr_sizes_survive_edit_before_incoming_field_is_known(self):
        self._competition(8)
        self.stage = self._swiss(
            format="SWISS_THRESHOLD", win_target=2, loss_limit=2, advancement_count=None
        )
        later = self._swiss(2, advancement_count=2)
        self._elimination(3)
        self.client.force_login(self.actor)
        response = self.client.post(
            self._setup_url(later),
            self._data(
                format="ROUND_ROBIN",
                tiebreak_1="HEAD_TO_HEAD",
                group_size_policy="EXACT",
                group_count=2,
                group_name_1="A",
                group_size_1=3,
                group_quota_1=1,
                group_name_2="B",
                group_size_2=3,
                group_quota_2=1,
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(later.group_plans.values_list("size", flat=True)), [3, 3])
        response = self.client.get(self._setup_url(later))
        form = response.context_data["form"]
        self.assertIsNone(form.incoming_count)
        self.assertEqual(form["group_size_policy"].value(), "EXACT")
        self.assertEqual(form["group_size_1"].value(), 3)
        self.assertEqual(form["group_size_2"].value(), 3)

    def test_fixed_and_threshold_ignore_irrelevant_fields(self):
        self._draw(publish=False)
        self.client.force_login(self.actor)
        response = self.client.post(
            self._setup_url(),
            self._data(format="SWISS_THRESHOLD", win_target=2, loss_limit=2),
        )
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        self.stage.refresh_from_db()
        self.assertIsNone(self.stage.advancement_count)
        self.assertIsNone(self.stage.swiss_round_count)
        self.assertEqual(self.stage.swiss_win_target, 2)
        response = self.client.post(
            self._setup_url(), self._data(win_target=999, loss_limit=999)
        )
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        self.stage.refresh_from_db()
        self.assertIsNone(self.stage.swiss_win_target)

    def test_private_swiss_tail_saves_but_publication_is_blocked(self):
        self._competition(5)
        self.stage = self._swiss(advancement_count=2)
        self.client.force_login(self.actor)
        response = self.client.post(self._setup_url(), self._data())
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        swiss_commands.save_swiss_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self._revision(),
            ordered_entrant_ids=[e.pk for e in self.entrants],
        )
        response = self.client.post(
            reverse(
                "admin:competitions_competition_publish_detail",
                args=[self.competition.pk],
            ),
            {"expected_revision": self._revision()},
        )
        self.assertContains(response, "cannot be the final stage")
        self.assertFalse(self.competition.stages.exclude(published_at=None).exists())

    def test_swiss_preview_refresh_is_read_only(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        saved = self._generate()
        revision = self._revision()
        self.client.force_login(self.actor)
        with patch.object(
            swiss_commands, "pair_swiss_round", side_effect=AssertionError("GET solved")
        ):
            first = self.client.get(
                workspace_url(self.competition.pk, "bracket", stage_id=self.stage.pk)
            )
            second = self.client.get(
                workspace_url(self.competition.pk, "standings", stage_id=self.stage.pk)
            )
            self.client.get(self._url("generate"))
            self.client.get(self._url("publish"))
        self.assertEqual(first.context_data["swiss_display"]["round"].pk, saved.pk)
        self.assertEqual(second.context_data["swiss_display"]["round"].pk, saved.pk)
        self.assertEqual(self._revision(), revision)
        self.assertContains(first, "Private preview")
        self.assertContains(first, "Cross-group")
        self.assertContains(second, "Opponent points")
        self.assertContains(second, "Bye count")

    def test_generate_and_publish_are_explicit_revision_checked_actions(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        self.client.force_login(self.actor)
        old_revision = self._revision()
        response = self.client.post(
            self._url("generate"), {"expected_revision": old_revision}
        )
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        self.assertEqual(
            response.url,
            workspace_url(self.competition.pk, "bracket", stage_id=self.stage.pk),
        )
        saved = draw.rounds.get(state="DRAFT")
        response = self.client.post(
            self._url("publish"), {"expected_revision": old_revision}
        )
        self.assertContains(response, "Reload and try again.", status_code=200)
        saved.refresh_from_db()
        self.assertEqual(saved.state, "DRAFT")
        response = self.client.post(
            self._url("publish"), {"expected_revision": self._revision()}
        )
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        saved.refresh_from_db()
        self.assertEqual(saved.state, "PUBLISHED")

    def test_private_and_historical_matches_have_no_mutation_actions(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        saved = self._generate()
        self.client.force_login(self.actor)
        for state in ("DRAFT", "SUPERSEDED"):
            saved.state = state
            saved.save(update_fields=["state"])
            match = saved.matches.first()
            response = self.client.get(
                reverse("admin:competitions_match_change", args=[match.pk])
            )
            self.assertEqual(response.context_data["match_actions"], [])
            self.assertIsNone(response.context_data["match_card"]["result_url"])
            self.assertIsNone(response.context_data["match_card"]["schedule_url"])

    def test_unauthorized_and_csrf_posts_do_not_change_rounds(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        actor = create_account(
            email="limited@example.com", password="strong-password", is_staff=True
        )
        actor.user_permissions.add(Permission.objects.get(codename="view_competition"))
        self.client.force_login(actor)
        self.assertEqual(
            self.client.post(
                self._url("generate"), {"expected_revision": self._revision()}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self._url("publish"), {"expected_revision": self._revision()}
            ).status_code,
            403,
        )
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.actor)
        self.assertEqual(
            csrf.post(
                self._url("generate"), {"expected_revision": self._revision()}
            ).status_code,
            403,
        )
        self.assertEqual(draw.rounds.count(), 1)

    def test_rematch_action_requires_actual_failed_generation_and_confirmation(self):
        draw = self._rematch_dead_end()
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(self._url("rematch")).status_code, 403)
        response = self.client.post(
            self._url("generate"), {"expected_revision": self._revision()}
        )
        self.assertContains(response, "Allow required rematches")
        token = response.context_data["rematch_token"]
        for data in ({}, {"confirm_rematches": "on"}, {"internal_reason": "Conflict"}):
            response = self.client.post(
                self._url("rematch"),
                dict(expected_revision=self._revision(), token=token, **data),
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(draw.rounds.filter(state="DRAFT").exists())
        response = self.client.post(
            self._url("rematch"),
            dict(
                expected_revision=self._revision(),
                token=token,
                confirm_rematches="on",
                internal_reason="No repeat-free complete solution",
            ),
        )
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )
        draft = draw.rounds.get(state="DRAFT")
        self.assertTrue(draft.rematches_authorized)
        response = self.client.post(
            self._url("publish"), {"expected_revision": self._revision()}
        )
        self.assertEqual(
            response.status_code,
            302,
            response.context_data["form"].errors if response.status_code == 200 else "",
        )

    def test_locked_plan_and_correction_retirement_details(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        second = self._generate()
        self._publish(second)
        self._finish(second)
        match = draw.rounds.get(number=1).matches.exclude(outcome="BYE").first()
        preview = commands.preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self._revision(),
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        display = correction_display(preview)
        self.assertEqual(display["swiss"]["rounds"][0]["id"], second.pk)
        self.assertTrue(display["swiss"]["played_matches"])
        self.client.force_login(self.actor)
        response = self.client.get(workspace_url(self.competition.pk, "setup"))
        self.assertContains(response, "whole stage plan is locked")
        self.assertNotContains(response, ">Edit stage</a>")

    def test_first_swiss_draw_uses_existing_seed_form(self):
        self._competition(5)
        self.stage = self._swiss(advancement_count=2)
        self._elimination(2)
        self.client.force_login(self.actor)
        url = (
            reverse(
                "admin:competitions_competition_draw_detail", args=[self.competition.pk]
            )
            + f"?stage={self.stage.pk}"
        )
        response = self.client.post(
            url,
            dict(
                expected_revision=self._revision(),
                **{f"seed_{index}": e.pk for index, e in enumerate(self.entrants, 1)},
            ),
        )
        self.assertEqual(response.status_code, 302)
        draw = self.stage.draws.get()
        self.assertEqual(draw.swiss_round_limit, 3)
        self.assertEqual(draw.rounds.get().state, "DRAFT")
        self.assertEqual(
            response.url, workspace_url(self.competition.pk, stage_id=self.stage.pk)
        )

    def test_cutoff_action_uses_current_qualification(self):
        draw = self._draw(count=8, round_count=1)
        self._finish(draw.rounds.get())
        self.client.force_login(self.actor)
        response = self.client.get(
            workspace_url(self.competition.pk, "standings", stage_id=self.stage.pk)
        )
        self.assertContains(response, "Resolve qualification tie")
        self.assertEqual(
            response.context_data["qualification_display"]["qualification_state"],
            "AWAITING_RESOLUTION",
        )

    def test_correction_review_renders_retired_rounds_and_played_results(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        second = self._generate()
        self._publish(second)
        self._finish(second)
        self.client.force_login(self.actor)
        target = draw.rounds.get(number=1).matches.exclude(outcome="BYE").first()
        response = self.client.post(
            reverse("admin:competitions_match_correct_detail", args=[target.pk]),
            dict(
                expected_revision=self._revision(),
                outcome="PLAYED",
                side_one_score=0,
                side_two_score=2,
            ),
        )
        self.assertContains(response, "Swiss rounds becoming historical")
        self.assertContains(response, "Played Swiss results preserved as history")
        self.assertContains(response, "Round 2, version 1")
        self.assertContains(response, 'name="token"')
        second.refresh_from_db()
        self.assertEqual(second.state, "PUBLISHED")

    def test_automatic_rr_sizes_appear_only_after_saved_actual_handoff(self):
        self._competition(13)
        self.stage = self._swiss(
            format="SWISS_THRESHOLD", win_target=1, loss_limit=1, advancement_count=None
        )
        destination = handoff_fixtures.SwissHandoffTests._rr(
            self, 2, [("A", None, 2), ("B", None, 2)]
        )
        source = handoff_fixtures.SwissHandoffTests._save_source(self)
        self._finish(source.rounds.get())
        from competitions.handoff_commands import generate_next_stage_draw

        saved = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self._revision(),
        )
        self.client.force_login(self.actor)
        response = self.client.get(
            workspace_url(self.competition.pk, "setup", stage_id=destination.pk)
        )
        row = next(
            r
            for r in response.context_data["plan_rows"]
            if r["stage"].pk == destination.pk
        )
        self.assertEqual(row["incoming_count"], 7)
        self.assertContains(response, "A: 4 entrants, 2 advance")
        self.assertContains(response, "B: 3 entrants, 2 advance")
        self.assertEqual(
            list(destination.group_plans.values_list("size", flat=True)), [None, None]
        )
        self.assertEqual(saved.entries.count(), 7)

    _publish_draw = handoff_fixtures.SwissHandoffTests._publish_draw

    def test_successor_workspace_explains_incompatible_locked_actual_field(self):
        self._competition(13)
        self.stage = self._swiss(
            format="SWISS_THRESHOLD", win_target=1, loss_limit=1, advancement_count=None
        )
        destination = self._swiss(2, round_count=8, advancement_count=2)
        self._elimination(3)
        source = handoff_fixtures.SwissHandoffTests._save_source(self)
        self._finish(source.rounds.get())
        self.client.force_login(self.actor)
        response = self.client.get(
            workspace_url(self.competition.pk, "setup", stage_id=destination.pk)
        )
        self.assertContains(response, "Choose 1–7 Swiss rounds for this field.")
        self.assertNotContains(response, "Ready for a saved random draw")
        self.assertIsNone(response.context_data["primary_action"])
