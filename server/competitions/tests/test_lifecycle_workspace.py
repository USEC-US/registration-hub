from django.test import TestCase
from django.urls import reverse

from competitions.tests import test_workspace as fixture_module

from competitions.models import CompetitionEntrant, ChangeSet
from competitions.tests import test_competition_lifecycle as ending_fixtures
from competitions.tests import test_entrant_lifecycle as entrant_fixtures


class LifecycleWorkspaceTests(TestCase):
    setUpTestData = classmethod(
        fixture_module.CompetitionWorkspaceTests.setUpTestData.__func__
    )
    setUp = fixture_module.CompetitionWorkspaceTests.setUp
    _draft = fixture_module.CompetitionWorkspaceTests._draft
    _grant_viewer = fixture_module.CompetitionWorkspaceTests._grant_viewer

    def url(self, competition, entrant):
        return reverse(
            "admin:competitions_entrant_transition", args=[competition.pk, entrant.pk]
        )

    def test_preview_confirm_and_read_only_get(self):
        competition, draw = self._draft(published=True)
        entrant = competition.entrants.first()
        url = self.url(competition, entrant)
        revision, history = competition.revision, ChangeSet.objects.count()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        competition.refresh_from_db()
        self.assertEqual(
            (competition.revision, ChangeSet.objects.count()), (revision, history)
        )
        response = self.client.post(
            url, {"expected_revision": revision, "status": "WITHDRAWN"}
        )
        self.assertEqual(response.status_code, 200)
        token = response.context["token"]
        self.assertContains(response, entrant.display_name)
        response = self.client.post(
            url, {"token": token, "internal_reason": "Private removal reason"}
        )
        self.assertEqual(response.status_code, 302)
        entrant.refresh_from_db()
        self.assertEqual(entrant.status, CompetitionEntrant.Status.WITHDRAWN)
        self.assertEqual(
            ChangeSet.objects.latest("pk").internal_reason, "Private removal reason"
        )

    def test_permission_scope_and_stale(self):
        competition, draw = self._draft(published=True)
        entrant, other = list(competition.entrants.all())[:2]
        url = self.url(competition, entrant)
        self._grant_viewer("view_competition")
        self.assertEqual(self.client.get(url).status_code, 403)
        self._grant_viewer("change_competition")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.organizer)
        response = self.client.post(
            url, {"expected_revision": competition.revision, "status": "WITHDRAWN"}
        )
        token = response.context["token"]
        response = self.client.post(
            self.url(competition, other),
            {"token": token, "internal_reason": "wrong subject"},
        )
        self.assertEqual(response.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.status, "ACTIVE")
        self.assertContains(response, "different")
        self.client.force_login(self.organizer)
        self.client.post(url, {"token": token, "internal_reason": "correct subject"})
        response = self.client.post(url, {"token": token, "internal_reason": "replay"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, "Reload and try again")

    def test_nonorganizer_inactive_and_private_history(self):
        competition, draw = self._draft(published=True)
        url = self.url(competition, competition.entrants.first())
        self._grant_viewer("view_competition", "change_competition", "change_match")
        self.assertEqual(self.client.get(url).status_code, 200)
        changes = (
            reverse("admin:competitions_competition_change", args=[competition.pk])
            + "?tab=changes"
        )
        self.assertEqual(self.client.get(changes).status_code, 403)
        self.viewer.groups.clear()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.viewer.groups.add(fixture_module.Group.objects.get(name="Organizers"))
        self.viewer.is_active = False
        self.viewer.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_live_forfeit_explicit_consent_and_private_reason_required(self):
        from competitions.commands import start_match
        from competitions.models import Match

        competition, draw = self._draft(published=True)
        match = draw.rounds.get(number=1).matches.get(status="PENDING")
        start_match(
            actor=self.organizer,
            match_id=match.pk,
            expected_revision=competition.revision,
        )
        competition.refresh_from_db()
        entrant = match.slots.get(position=1).resolved_entry.entrant
        url = self.url(competition, entrant)
        response = self.client.post(
            url, {"expected_revision": competition.revision, "status": "WITHDRAWN"}
        )
        token = response.context["token"]
        self.assertContains(response, "I confirm forfeiting")
        self.assertContains(response, match.code)
        self.assertContains(response, entrant.display_name)
        self._grant_viewer("change_competition")
        denied = self.client.post(
            url,
            {
                "token": token,
                "internal_reason": "Unavailable",
                "confirm_live_forfeits": "on",
            },
        )
        self.assertEqual(denied.status_code, 200)
        self.assertTrue(denied.context["form"].errors)
        entrant.refresh_from_db()
        self.assertEqual(entrant.status, "ACTIVE")
        self._grant_viewer("change_competition", "change_match")
        response = self.client.post(
            url, {"token": token, "internal_reason": "Unavailable"}
        )
        self.assertTrue(response.context["form"].errors)
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.LIVE)
        response = self.client.post(
            url, {"token": token, "confirm_live_forfeits": "on"}
        )
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(
            url,
            {
                "token": token,
                "internal_reason": "Unavailable",
                "confirm_live_forfeits": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        match.refresh_from_db()
        self.assertEqual(match.outcome, "FORFEIT")


class EndingWorkspaceTests(TestCase):
    setUp = ending_fixtures.CompetitionLifecycleTests.setUp
    _registration = ending_fixtures.CompetitionLifecycleTests._registration
    _chain = ending_fixtures.CompetitionLifecycleTests._chain
    _finish = ending_fixtures.CompetitionLifecycleTests._finish
    remove = ending_fixtures.CompetitionLifecycleTests.remove
    preview = ending_fixtures.CompetitionLifecycleTests.preview

    def test_end_reopen_read_only_and_explicit_consent(self):
        self.source, destination = self._chain()
        self._finish(self.source)
        self.remove(self.source.entries.first().entrant)
        self.competition.refresh_from_db()
        self.client.force_login(self.actor)
        url = reverse(
            "admin:competitions_competition_end",
            args=[self.competition.pk, self.source.stage_id],
        )
        revision, history = self.competition.revision, ChangeSet.objects.count()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.competition.refresh_from_db()
        self.assertEqual(
            (self.competition.revision, ChangeSet.objects.count()), (revision, history)
        )
        response = self.client.post(url, {"expected_revision": revision})
        self.assertContains(response, "Review lifecycle impact")
        token = response.context["token"]
        response = self.client.post(
            url, {"token": token, "internal_reason": "Cannot continue"}
        )
        self.assertEqual(response.status_code, 302)
        self.competition.refresh_from_db()
        self.assertIsNotNone(self.competition.ended_at)
        workspace = reverse(
            "admin:competitions_competition_change", args=[self.competition.pk]
        )
        response = self.client.get(workspace + "?tab=entrants")
        self.assertContains(response, "Reopen competition")
        self.assertNotContains(response, "Change availability")
        self.assertNotContains(response, ">End competition<")
        self.assertContains(
            self.client.get(workspace + "?tab=bracket"), "Closed · historical"
        )
        from competitions.admin_workspace import match_card

        self.assertTrue(
            match_card(self.source.rounds.first().matches.first(), self.actor)[
                "historical"
            ]
        )
        closed_match = self.source.rounds.first().matches.first()
        detail_url = reverse("admin:competitions_match_change", args=[closed_match.pk])
        self.assertContains(self.client.get(detail_url), "Closed source contest")
        round_url = reverse(
            "admin:competitions_round_change", args=[closed_match.round_id]
        )
        self.assertNotContains(self.client.get(round_url), "Set series length")
        reopen_url = reverse(
            "admin:competitions_competition_reopen", args=[self.competition.pk]
        )
        revision, history = self.competition.revision, ChangeSet.objects.count()
        response = self.client.get(reopen_url)
        self.assertContains(response, "fresh replacement previews")
        self.assertEqual(ChangeSet.objects.count(), history)
        response = self.client.post(reopen_url, {"expected_revision": revision})
        token = response.context["token"]
        response = self.client.post(
            reopen_url, {"token": token, "internal_reason": "Recover"}
        )
        self.assertTrue(response.context["form"].errors)
        self.competition.refresh_from_db()
        self.assertIsNotNone(self.competition.ended_at)
        response = self.client.post(
            reopen_url,
            {"token": token, "internal_reason": "Recover", "confirm_resets": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.competition.refresh_from_db()
        self.assertIsNone(self.competition.ended_at)

    def test_viable_continuation_feedback_and_wrong_operation_scope(self):
        self.source, destination = self._chain()
        self.client.force_login(self.actor)
        self.competition.refresh_from_db()
        url = reverse(
            "admin:competitions_competition_end",
            args=[self.competition.pk, self.source.stage_id],
        )
        revision, history = self.competition.revision, ChangeSet.objects.count()
        response = self.client.post(url, {"expected_revision": revision})
        self.assertContains(response, "locked continuation is still possible")
        self.assertIsNone(response.context["token"])
        self.assertEqual(ChangeSet.objects.count(), history)
        self._finish(self.source)
        self.remove(self.source.entries.first().entrant)
        self.competition.refresh_from_db()
        response = self.client.post(
            url, {"expected_revision": self.competition.revision}
        )
        token = response.context["token"]
        wrong_stage = reverse(
            "admin:competitions_competition_end",
            args=[self.competition.pk, destination.pk],
        )
        response = self.client.post(
            wrong_stage, {"token": token, "internal_reason": "Wrong stage"}
        )
        self.assertContains(response, "different operation or subject")
        entrant = self.source.entries.first().entrant
        wrong_operation = reverse(
            "admin:competitions_entrant_transition",
            args=[self.competition.pk, entrant.pk],
        )
        response = self.client.post(
            wrong_operation, {"token": token, "internal_reason": "Wrong operation"}
        )
        self.assertContains(response, "different operation or subject")
        self.competition.refresh_from_db()
        self.assertIsNone(self.competition.ended_at)

    def test_played_retired_suffix_names_and_permission_matrix(self):
        from competitions import commands
        from competitions.handoff_commands import generate_next_stage_draw
        from accounts.tests.factories import create_account
        from django.contrib.auth.models import Group, Permission

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
        self.competition.refresh_from_db()
        url = reverse(
            "admin:competitions_competition_end",
            args=[self.competition.pk, self.source.stage_id],
        )
        viewer = create_account(
            email="ending-viewer@example.com",
            password="strong-password",
            first_name="End",
            last_name="Viewer",
            is_staff=True,
        )
        viewer.groups.add(Group.objects.get_or_create(name="Organizers")[0])
        for perms, allowed_get, allowed_preview in [
            (["view_competition"], False, False),
            (["change_competition"], True, False),
            (["change_competition", "change_match"], True, True),
        ]:
            with self.subTest(perms=perms):
                viewer.user_permissions.set(
                    Permission.objects.filter(
                        content_type__app_label="competitions", codename__in=perms
                    )
                )
                self.client.force_login(viewer)
                self.assertEqual(
                    self.client.get(url).status_code, 200 if allowed_get else 403
                )
                response = self.client.post(
                    url, {"expected_revision": self.competition.revision}
                )
                if allowed_get:
                    self.assertEqual(bool(response.context["token"]), allowed_preview)
                else:
                    self.assertEqual(response.status_code, 403)
        self.client.force_login(self.actor)
        response = self.client.post(
            url, {"expected_revision": self.competition.revision}
        )
        token = response.context["token"]
        self.assertContains(response, destination.name)
        for match in suffix.rounds.first().matches.all():
            self.assertContains(response, match.code)
            for slot in match.slots.all():
                self.assertContains(response, slot.resolved_entry.entrant.display_name)
        self.assertContains(response, "I confirm the listed resets")
        response = self.client.post(
            url, {"token": token, "internal_reason": "Retire played suffix"}
        )
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(
            url,
            {
                "token": token,
                "internal_reason": "Retire played suffix",
                "confirm_resets": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        suffix.refresh_from_db()
        self.assertEqual(suffix.state, "SUPERSEDED")
        retired_match = suffix.rounds.first().matches.first()
        retired_detail = self.client.get(
            reverse("admin:competitions_match_change", args=[retired_match.pk])
        )
        self.assertContains(retired_detail, "earlier bracket")
        self.assertNotContains(retired_detail, "Closed source contest")
        reopen_url = reverse(
            "admin:competitions_competition_reopen", args=[self.competition.pk]
        )
        viewer.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="competitions", codename="change_competition"
            )
        )
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reopen_url).status_code, 403)
        self.assertEqual(
            self.client.post(
                reopen_url, {"expected_revision": self.competition.revision}
            ).status_code,
            403,
        )
        viewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="competitions", codename="change_match"
            )
        )
        self.assertEqual(self.client.get(reopen_url).status_code, 200)
        self.client.force_login(self.actor)
        workspace = (
            reverse("admin:competitions_competition_change", args=[self.competition.pk])
            + f"?stage={destination.pk}"
        )
        self.assertContains(self.client.get(workspace), "Historical stage")


class RestoreWorkspaceTests(TestCase):
    setUp = entrant_fixtures.EntrantLifecycleTests.setUp
    _registration = entrant_fixtures.EntrantLifecycleTests._registration
    _published_draw = entrant_fixtures.EntrantLifecycleTests._published_draw
    setup_draw = entrant_fixtures.EntrantLifecycleTests.setup_draw
    transition = entrant_fixtures.EntrantLifecycleTests.transition
    preview = entrant_fixtures.EntrantLifecycleTests.preview
    apply = entrant_fixtures.EntrantLifecycleTests.apply

    def test_restore_preview_names_independent_correction(self):
        from competitions import commands

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
            actor=self.actor, token=correction["token"], internal_reason="Independent"
        )
        self.competition.refresh_from_db()
        self.client.force_login(self.actor)
        url = reverse(
            "admin:competitions_entrant_transition",
            args=[self.competition.pk, self.entrant.pk],
        )
        response = self.client.post(
            url, {"expected_revision": self.competition.revision, "status": "ACTIVE"}
        )
        self.assertContains(response, "Independent corrections preserved")
        self.assertTrue(response.context["lifecycle_display"]["preserved"])
        self.assertContains(response, self.match.code)
        response = self.client.post(
            url, {"token": response.context["token"], "internal_reason": "Available"}
        )
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.assertEqual(self.match.outcome, "PLAYED")
