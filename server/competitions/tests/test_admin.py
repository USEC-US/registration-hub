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
