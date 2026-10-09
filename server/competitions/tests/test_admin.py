from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tests.factories import create_account
from competitions.models import (
    ChangeSet,
    Competition,
    Match,
    MatchSlot,
    Round,
    Stage,
    StageDraw,
    StageEntry,
)
from registrations.models import Registration, RegistrationMember
from tournaments.models import Game, Tournament, TournamentGame


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class CompetitionAdminTests(TestCase):
    def setUp(self):
        self.organizer = create_account(
            email="organizer@example.com",
            password="strong-password",
            first_name="Organizer",
            last_name="Admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.organizer)
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(
            name="Admin Cup", slug="admin-cup", is_published=True
        )
        self.division = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        self.registrations = [self._registration(index) for index in range(1, 4)]

    def _registration(self, index):
        registration = Registration.objects.create(
            tournament_game=self.division,
            status=Registration.Status.APPROVED,
            fee_amount_snapshot="0.00",
            fee_currency_snapshot="VND",
        )
        RegistrationMember.objects.create(
            registration=registration,
            gamer_tag_snapshot=f"Admin Player {index}",
            is_captain=True,
            display_order=1,
        )
        return registration

    def _publish(self, entrant_count=3):
        create_url = reverse(
            "admin:competitions_competition_create_for_division",
            args=[self.division.pk],
        )
        self.assertRedirects(
            self.client.post(create_url),
            reverse(
                "admin:competitions_competition_change",
                args=[self.division.competition.pk],
            ),
        )
        competition = Competition.objects.get(tournament_game=self.division)
        self.assertRedirects(
            self.client.post(
                reverse(
                    "admin:competitions_competition_configure_detail",
                    args=[competition.pk],
                ),
                {
                    "name": "Final bracket",
                    "default_series_length": 3,
                    "expected_revision": competition.revision,
                },
            ),
            reverse("admin:competitions_competition_change", args=[competition.pk]),
        )
        competition.refresh_from_db()
        self.assertRedirects(
            self.client.post(
                reverse(
                    "admin:competitions_competition_entrants_detail",
                    args=[competition.pk],
                ),
                {
                    "registrations": [
                        item.pk for item in self.registrations[:entrant_count]
                    ],
                    "expected_revision": competition.revision,
                },
            ),
            reverse("admin:competitions_competition_change", args=[competition.pk]),
        )
        competition.refresh_from_db()
        entrants = list(competition.entrants.order_by("pk"))
        self.assertRedirects(
            self.client.post(
                reverse(
                    "admin:competitions_competition_draw_detail",
                    args=[competition.pk],
                ),
                {
                    "expected_revision": competition.revision,
                    **{
                        f"seed_{index}": entrant.pk
                        for index, entrant in enumerate(entrants, 1)
                    },
                },
            ),
            reverse("admin:competitions_competition_change", args=[competition.pk]),
        )
        competition.refresh_from_db()
        self.assertRedirects(
            self.client.post(
                reverse(
                    "admin:competitions_competition_publish_detail",
                    args=[competition.pk],
                ),
                {"expected_revision": competition.revision},
            ),
            reverse("admin:competitions_competition_change", args=[competition.pk]),
        )
        competition.refresh_from_db()
        return competition, competition.stages.get().draws.get(
            state=StageDraw.State.PUBLISHED
        )

    def test_division_link_and_create_confirmation_are_csrf_protected(self):
        division_admin = admin.site.get_model_admin(TournamentGame)
        request = RequestFactory().get("/admin/")
        request.user = self.organizer
        create_url = reverse(
            "admin:competitions_competition_create_for_division",
            args=[self.division.pk],
        )
        self.assertIn(create_url, division_admin.competition_link(self.division))

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.organizer)
        response = csrf_client.get(create_url)
        self.assertContains(response, "Create competition")
        self.assertFalse(Competition.objects.exists())
        self.assertEqual(csrf_client.post(create_url).status_code, 403)
        response = csrf_client.post(
            create_url,
            {"csrfmiddlewaretoken": csrf_client.cookies["csrftoken"].value},
        )
        competition = Competition.objects.get(tournament_game=self.division)
        self.assertRedirects(
            response,
            reverse("admin:competitions_competition_change", args=[competition.pk]),
        )
        self.division.refresh_from_db()
        self.assertIn(
            reverse("admin:competitions_competition_change", args=[competition.pk]),
            division_admin.competition_link(self.division),
        )

    def test_create_requires_both_organizer_membership_and_exact_permission(self):
        staff = create_account(
            email="limited@example.com",
            password="strong-password",
            first_name="Limited",
            last_name="Staff",
            is_staff=True,
        )
        permission = Permission.objects.get(
            content_type__app_label="competitions", codename="add_competition"
        )
        url = reverse(
            "admin:competitions_competition_create_for_division",
            args=[self.division.pk],
        )
        self.client.force_login(staff)
        staff.user_permissions.add(permission)
        self.assertEqual(self.client.get(url).status_code, 403)

        group = Group.objects.create(name="Organizers")
        staff.groups.add(group)
        staff.user_permissions.remove(permission)
        staff = type(staff).objects.get(pk=staff.pk)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 403)

        staff.user_permissions.add(permission)
        staff = type(staff).objects.get(pk=staff.pk)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_action_rejects_revision_rendered_before_another_mutation(self):
        self.client.post(
            reverse(
                "admin:competitions_competition_create_for_division",
                args=[self.division.pk],
            )
        )
        competition = Competition.objects.get(tournament_game=self.division)
        url = reverse(
            "admin:competitions_competition_configure_detail", args=[competition.pk]
        )
        response = self.client.get(url)
        self.assertContains(response, 'name="expected_revision"')
        rendered_revision = response.context["form"]["expected_revision"].value()

        self.assertRedirects(
            self.client.post(
                url,
                {
                    "name": "Final bracket",
                    "default_series_length": 3,
                    "expected_revision": rendered_revision,
                },
            ),
            reverse("admin:competitions_competition_change", args=[competition.pk]),
        )
        competition.refresh_from_db()
        current_revision = competition.revision

        response = self.client.post(
            url,
            {
                "name": "Stale overwrite",
                "default_series_length": 5,
                "expected_revision": rendered_revision,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Competition changed from revision")
        competition.refresh_from_db()
        self.assertEqual(competition.revision, current_revision)
        self.assertEqual(competition.stages.get().name, "Final bracket")

    def test_setup_entrants_draw_publish_and_round_override(self):
        competition, draw = self._publish()
        self.assertEqual(competition.entrants.count(), 3)
        self.assertEqual(draw.entries.count(), 3)
        self.assertEqual(draw.rounds.count(), 2)
        self.assertEqual(Match.objects.filter(round__draw=draw).count(), 3)
        self.assertIsNotNone(draw.published_at)

        round_ = draw.rounds.get(number=2)
        url = reverse("admin:competitions_round_series_detail", args=[round_.pk])
        self.assertContains(self.client.get(url), "Set round series length")
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertRedirects(
            self.client.post(
                url,
                {"series_length": 5, "expected_revision": competition.revision},
            ),
            reverse("admin:competitions_competition_change", args=[competition.pk])
            + "?tab=bracket",
        )
        round_.refresh_from_db()
        self.assertEqual(round_.series_length_override, 5)

    def test_finalize_and_confirm_correction_keeps_impact_on_form_error(self):
        competition, draw = self._publish(entrant_count=2)
        match = Match.objects.get(round__draw=draw)
        finalize_url = reverse(
            "admin:competitions_match_finalize_detail", args=[match.pk]
        )
        self.assertRedirects(
            self.client.post(
                finalize_url,
                {
                    "outcome": Match.Outcome.PLAYED,
                    "side_one_score": 2,
                    "side_two_score": 0,
                    "winner_position": "",
                    "expected_revision": competition.revision,
                },
            ),
            reverse("admin:competitions_match_change", args=[match.pk]),
        )
        match.refresh_from_db()
        competition.refresh_from_db()
        old_winner_id = match.winner_id

        correct_url = reverse(
            "admin:competitions_match_correct_detail", args=[match.pk]
        )
        response = self.client.post(
            correct_url,
            {
                "outcome": Match.Outcome.PLAYED,
                "side_one_score": 0,
                "side_two_score": 2,
                "winner_position": "",
                "expected_revision": competition.revision,
            },
        )
        self.assertEqual(response.status_code, 200)
        token = response.context["token"]
        self.assertContains(response, "Review this correction")

        response = self.client.post(
            correct_url, {"token": token, "internal_reason": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review this correction")
        self.assertContains(response, "This field is required")

        self.assertRedirects(
            self.client.post(
                correct_url,
                {
                    "token": token,
                    "internal_reason": "Scores were entered on the wrong sides.",
                },
            ),
            reverse("admin:competitions_match_change", args=[match.pk]),
        )
        match.refresh_from_db()
        competition.refresh_from_db()
        self.assertNotEqual(match.winner_id, old_winner_id)
        change = competition.changes.get(revision=competition.revision)
        self.assertEqual(change.kind, "result_corrected")
        self.assertEqual(
            change.internal_reason, "Scores were entered on the wrong sides."
        )

    def test_generated_records_have_no_direct_edit_surface(self):
        competition, draw = self._publish()
        objects = (
            (Stage, competition.stages.get()),
            (StageDraw, draw),
            (StageEntry, draw.entries.first()),
            (Round, draw.rounds.first()),
            (Match, Match.objects.filter(round__draw=draw).first()),
            (
                MatchSlot,
                MatchSlot.objects.filter(match__round__draw=draw).first(),
            ),
            (ChangeSet, competition.changes.first()),
        )
        request = RequestFactory().get("/admin/")
        request.user = self.organizer
        for model, obj in objects:
            with self.subTest(model=model.__name__):
                model_admin = admin.site.get_model_admin(model)
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request, obj))
                self.assertEqual(
                    set(model_admin.get_readonly_fields(request, obj)),
                    {field.name for field in model._meta.fields},
                )


class RoundRobinAdminTests(TestCase):
    setUp = CompetitionAdminTests.setUp
    _registration = CompetitionAdminTests._registration

    def action(self, name, data=None):
        self.competition.refresh_from_db()
        url = reverse(
            f"admin:competitions_competition_{name}_detail", args=[self.competition.pk]
        )
        return self.client.post(
            url, {"expected_revision": self.competition.revision, **(data or {})}
        )

    def setup_rr(self, **rules):
        from competitions.commands import create_competition

        self.competition = create_competition(
            actor=self.organizer, tournament_game_id=self.division.pk
        )
        response = self.action(
            "configure",
            {
                "name": "Groups",
                "format": "ROUND_ROBIN",
                "series_mode": "FIXED_GAMES",
                "default_series_length": 2,
                "meetings": 1,
                "win_points": "3.00",
                "draw_points": "1.00",
                "loss_points": "0.00",
                "tiebreak_1": "",
                "tiebreak_2": "",
                "tiebreak_3": "",
                "tiebreak_4": "",
                **rules,
            },
        )
        self.assertEqual(response.status_code, 302)
        return self.competition.stages.get()

    def published_rr(self):
        self.stage = self.setup_rr()
        self.assertEqual(
            self.action(
                "entrants", {"registrations": [r.pk for r in self.registrations]}
            ).status_code,
            302,
        )
        ids = list(self.competition.entrants.values_list("pk", flat=True))
        response = self.action(
            "draw",
            {
                "group_specs": "Alpha | 1",
                "allocation": "MANUAL",
                **{f"seed_{i}": pk for i, pk in enumerate(ids, 1)},
                **{f"group_{pk}": 1 for pk in ids},
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.action("publish").status_code, 302)
        self.draw = self.stage.draws.get(state="PUBLISHED")
        self.group = self.draw.groups.get()
        return ids

    def test_ordered_rule_controls_and_invalid_duplicate_rules(self):
        stage = self.setup_rr(tiebreak_1="MATCH_WINS", tiebreak_4="HEAD_TO_HEAD")
        self.assertEqual(stage.tiebreaks, ["MATCH_WINS", "HEAD_TO_HEAD"])
        self.competition.refresh_from_db()
        revision = self.competition.revision
        response = self.action(
            "configure",
            {
                "name": "Groups",
                "format": "ROUND_ROBIN",
                "series_mode": "FIXED_GAMES",
                "default_series_length": 2,
                "meetings": 1,
                "win_points": "3",
                "draw_points": "1",
                "loss_points": "0",
                "tiebreak_1": "HEAD_TO_HEAD",
                "tiebreak_4": "HEAD_TO_HEAD",
            },
        )
        self.assertContains(response, "at most once")
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.revision, revision)
        form = self.client.get(
            reverse(
                "admin:competitions_competition_configure_detail",
                args=[self.competition.pk],
            )
        )
        self.assertContains(form, "Tiebreaker 4")
        self.assertContains(form, "Head-to-head points")

    def test_saved_draw_preview_includes_standings_rules(self):
        self.setup_rr(tiebreak_1="MATCH_WINS", tiebreak_4="HEAD_TO_HEAD")
        self.action("entrants", {"registrations": [r.pk for r in self.registrations]})
        ids = list(self.competition.entrants.values_list("pk", flat=True))
        self.action(
            "draw",
            {
                "group_specs": "Alpha | 1",
                "allocation": "SNAKE",
                **{f"seed_{i}": pk for i, pk in enumerate(ids, 1)},
            },
        )
        url = reverse(
            "admin:competitions_competition_change", args=[self.competition.pk]
        )
        for tab in ("bracket", "setup"):
            with self.subTest(tab=tab):
                response = self.client.get(url, {"tab": tab})
                self.assertContains(response, "Standings rules")
                self.assertContains(response, "Meetings per pair")
                self.assertContains(response, "3.00 / 1.00 / 0.00")
                self.assertContains(response, "Match wins → Head-to-head points")

    def test_publish_fixed_draw_standings_and_confirm_manual_tie(self):
        self.published_rr()
        for match in Match.objects.filter(round__draw=self.draw):
            self.competition.refresh_from_db()
            url = reverse("admin:competitions_match_finalize_detail", args=[match.pk])
            form = self.client.get(url)
            self.assertContains(form, "Fixed 2 games")
            response = self.client.post(
                url,
                {
                    "expected_revision": self.competition.revision,
                    "outcome": "PLAYED",
                    "side_one_score": 1,
                    "side_two_score": 1,
                },
            )
            self.assertEqual(response.status_code, 302)
        url = (
            reverse("admin:competitions_competition_change", args=[self.competition.pk])
            + "?tab=standings"
        )
        response = self.client.get(url)
        self.assertContains(response, "Awaiting resolution")
        preview_url = reverse(
            "admin:competitions_group_tie_preview", args=[self.group.pk]
        )
        form = self.client.get(preview_url)
        self.competition.refresh_from_db()
        ids = list(self.group.entries.values_list("pk", flat=True))
        response = self.client.post(
            preview_url,
            {
                "expected_revision": self.competition.revision,
                "method": "MANUAL",
                "series_length": 1,
                **{f"order_{i}": pk for i, pk in enumerate(reversed(ids), 1)},
            },
        )
        self.assertContains(response, "Review qualification tie")
        token = response.context_data["token"]
        confirm_url = reverse(
            "admin:competitions_group_tie_confirm", args=[self.group.pk]
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.organizer)
        self.assertEqual(
            csrf_client.post(
                confirm_url, {"token": token, "internal_reason": "Choice"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                confirm_url, {"token": token, "internal_reason": "PRIVATE-CHOICE"}
            ).status_code,
            302,
        )
        response = self.client.get(url)
        self.assertContains(response, "Qualified")
        self.assertEqual(
            self.client.post(
                confirm_url, {"token": token, "internal_reason": "Repeat"}
            ).status_code,
            200,
        )
        self.assertEqual(self.group.tie_resolutions.count(), 1)
        self.assertEqual(
            self.action(
                "configure",
                {
                    "name": "Changed",
                    "format": "ROUND_ROBIN",
                    "series_mode": "BEST_OF",
                    "default_series_length": 3,
                    "meetings": 2,
                    "win_points": "3",
                    "draw_points": "1",
                    "loss_points": "0",
                },
            ).status_code,
            200,
        )
        self.stage.refresh_from_db()
        self.assertEqual(self.stage.name, "Groups")

    def test_extra_tie_preview_tampering_permissions_and_historical_controls(self):
        from competitions.commands import (
            finalize_match,
            preview_correction,
            apply_correction,
        )
        from competitions.round_robin_commands import (
            preview_group_tie,
            confirm_group_tie,
        )

        self.published_rr()
        for match in Match.objects.filter(round__draw=self.draw):
            self.competition.refresh_from_db()
            finalize_match(
                actor=self.organizer,
                match_id=match.pk,
                expected_revision=self.competition.revision,
                outcome="PLAYED",
                side_one_score=1,
                side_two_score=1,
            )
        self.competition.refresh_from_db()
        ids = list(self.group.entries.values_list("pk", flat=True))
        preview = preview_group_tie(
            actor=self.organizer,
            group_id=self.group.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=ids,
            method="EXTRA_MATCHES",
        )
        confirm_url = reverse(
            "admin:competitions_group_tie_confirm", args=[self.group.pk]
        )
        self.assertEqual(
            self.client.post(
                confirm_url, {"token": preview["token"] + "tampered"}
            ).status_code,
            200,
        )
        self.assertEqual(self.group.tie_resolutions.count(), 0)
        resolution = confirm_group_tie(actor=self.organizer, token=preview["token"])
        target = Match.objects.filter(
            round__draw=self.draw, round__section="NORMAL"
        ).first()
        self.competition.refresh_from_db()
        correction = preview_correction(
            actor=self.organizer,
            match_id=target.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        apply_correction(
            actor=self.organizer, token=correction["token"], internal_reason="Typo"
        )
        extra = Match.objects.filter(round__tie_resolution=resolution).first()
        response = self.client.get(
            reverse("admin:competitions_match_change", args=[extra.pk])
        )
        self.assertContains(response, "kept here for reference")
        self.assertNotContains(response, "Enter result")
        limited = create_account(
            email="rr-limited@example.com", password="strong-password", is_staff=True
        )
        self.client.force_login(limited)
        preview_url = reverse(
            "admin:competitions_group_tie_preview", args=[self.group.pk]
        )
        self.assertEqual(self.client.get(preview_url).status_code, 403)
        self.assertEqual(
            self.client.post(confirm_url, {"token": preview["token"]}).status_code, 403
        )
