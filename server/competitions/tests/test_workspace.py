from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tests.factories import create_account
from competitions.admin_workspace import match_card
from competitions.commands import (
    configure_elimination,
    create_competition,
    finalize_match,
    publish_draw,
    save_elimination_draw,
    select_entrants,
)
from competitions.models import Competition, Match, Stage, StageDraw
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
class CompetitionWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = create_account(
            email="workspace-admin@example.com",
            password="strong-password",
            first_name="Workspace",
            last_name="Organizer",
            is_staff=True,
            is_superuser=True,
        )
        cls.viewer = create_account(
            email="workspace-viewer@example.com",
            password="strong-password",
            first_name="Workspace",
            last_name="Viewer",
            is_staff=True,
        )
        cls.viewer.groups.add(Group.objects.get_or_create(name="Organizers")[0])
        game = Game.objects.create(name="Chess", slug="workspace-chess")
        tournament = Tournament.objects.create(
            name="Workspace Cup", slug="workspace-cup", is_published=True
        )
        cls.division = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        cls.registrations = []
        for name in ("An Nguyen", "Binh Tran", "Chi Le"):
            registration = Registration.objects.create(
                tournament_game=cls.division,
                status=Registration.Status.APPROVED,
                fee_amount_snapshot="0.00",
                fee_currency_snapshot="VND",
            )
            RegistrationMember.objects.create(
                registration=registration,
                gamer_tag_snapshot=name,
                is_captain=True,
                display_order=1,
            )
            cls.registrations.append(registration)

    def setUp(self):
        self.client.force_login(self.organizer)

    def _url(self, action, obj=None, model="competition"):
        return reverse(
            f"admin:competitions_{model}_{action}",
            args=[obj.pk] if obj is not None else None,
        )

    def _grant_viewer(self, *codenames):
        self.viewer.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="competitions", codename__in=codenames
            )
        )
        self.client.force_login(self.viewer)

    def _draft(self, *, published=False):
        competition = create_competition(
            actor=self.organizer, tournament_game_id=self.division.pk
        )
        configure_elimination(
            format="SINGLE_ELIMINATION",
            actor=self.organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            name="Playoffs",
            default_series_length=3,
        )
        competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            registration_ids=[item.pk for item in self.registrations],
        )
        competition.refresh_from_db()
        draw = save_elimination_draw(
            actor=self.organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            entrant_order=[item.pk for item in entrants],
        )
        competition.refresh_from_db()
        if published:
            draw = publish_draw(
                actor=self.organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
            )
            competition.refresh_from_db()
        return competition, draw

    def test_forfeit_cards_label_winner_without_replacing_recorded_scores(self):
        competition, draw = self._draft(published=True)
        match = Match.objects.get(
            round__draw=draw, round__number=1, status=Match.Status.PENDING
        )
        slots = list(match.slots.order_by("position"))
        finalize_match(
            actor=self.organizer,
            match_id=match.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.FORFEIT,
            side_one_score=1,
            side_two_score=0,
            winner_position=2,
        )
        match.refresh_from_db()
        self.assertEqual(
            [slot["score"] for slot in match_card(match, self.organizer)["slots"]],
            ["FF", "W"],
        )
        self.assertEqual((match.side_one_score, match.side_two_score), (1, 0))

        match.winner_id = slots[0].resolved_entry_id
        self.assertEqual(
            [slot["score"] for slot in match_card(match, self.organizer)["slots"]],
            ["W", "FF"],
        )
        match.outcome = Match.Outcome.PLAYED
        self.assertEqual(
            [slot["score"] for slot in match_card(match, self.organizer)["slots"]],
            [1, 0],
        )

    def _primary_action(self, competition, expected_url):
        response = self.client.get(self._url("change", competition))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["primary_action"]["url"], expected_url)
        self.assertContains(response, f'href="{expected_url}"')
        return response

    def _submit(self, competition, action, data):
        competition.refresh_from_db()
        response = self.client.post(
            self._url(action, competition),
            {"expected_revision": competition.revision, **data},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(self._url("change", competition)))
        competition.refresh_from_db()

    def _publish_double_workspace(self, policy, *, entrant_count=3):
        self.client.post(self._url("add"), {"tournament_game": self.division.pk})
        competition = Competition.objects.get(tournament_game=self.division)
        self._submit(
            competition,
            "configure_detail",
            {
                "name": "Double elimination playoffs",
                "format": Stage.Format.DOUBLE_ELIMINATION,
                "grand_final_policy": policy,
                "default_series_length": 3,
            },
        )
        self._submit(
            competition,
            "entrants_detail",
            {"registrations": [item.pk for item in self.registrations[:entrant_count]]},
        )
        self._submit(
            competition,
            "draw_detail",
            {
                f"seed_{number}": entrant.pk
                for number, entrant in enumerate(competition.entrants.order_by("pk"), 1)
            },
        )
        preview = self.client.get(self._url("change", competition))
        publication = self.client.get(self._url("publish_detail", competition))
        self._submit(competition, "publish_detail", {})
        draw = StageDraw.objects.get(
            stage__competition=competition, state=StageDraw.State.PUBLISHED
        )
        return competition, draw, preview, publication

    def test_only_competitions_are_listed_even_for_superusers(self):
        self.viewer.user_permissions.set(
            Permission.objects.filter(content_type__app_label="competitions")
        )
        for user in (self.organizer, self.viewer):
            with self.subTest(user=user.email):
                request = RequestFactory().get("/admin/")
                request.user = user
                app = next(
                    app
                    for app in admin.site.get_app_list(request)
                    if app["app_label"] == "competitions"
                )
                self.assertEqual(
                    [model["object_name"] for model in app["models"]],
                    ["Competition"],
                )

    def test_guided_workspace_reaches_named_result_and_advances_winner(self):
        add_url = self._url("add")
        self.assertContains(self.client.get(self._url("changelist")), add_url)
        self.assertContains(self.client.get(add_url), "Workspace Cup")
        response = self.client.post(add_url, {"tournament_game": self.division.pk})
        competition = Competition.objects.get(tournament_game=self.division)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(self._url("change", competition)))

        response = self._primary_action(
            competition, self._url("configure_detail", competition)
        )
        self.assertEqual(response.context["tab"], "setup")
        self._submit(
            competition,
            "configure_detail",
            {"name": "Playoffs", "default_series_length": 3},
        )
        self._primary_action(competition, self._url("entrants_detail", competition))
        entrants_page = self.client.get(self._url("entrants_detail", competition))
        for name in ("An Nguyen", "Binh Tran", "Chi Le"):
            self.assertContains(entrants_page, name)
        self._submit(
            competition,
            "entrants_detail",
            {"registrations": [item.pk for item in self.registrations]},
        )
        self._primary_action(competition, self._url("draw_detail", competition))
        self._submit(
            competition,
            "draw_detail",
            {
                f"seed_{number}": entrant.pk
                for number, entrant in enumerate(competition.entrants.order_by("pk"), 1)
            },
        )
        response = self._primary_action(
            competition, self._url("publish_detail", competition)
        )
        self.assertEqual(response.context["tab"], "bracket")
        self._submit(competition, "publish_detail", {})

        match = Match.objects.get(
            round__draw__stage__competition=competition,
            round__number=1,
            status=Match.Status.PENDING,
        )
        result_url = self._url("finalize_detail", match, "match")
        self._primary_action(competition, result_url)
        match_page = self.client.get(self._url("change", match, "match"))
        self.assertContains(match_page, result_url)
        self.assertContains(match_page, self._url("schedule_detail", match, "match"))
        self.assertContains(match_page, self._url("change", competition))
        self.assertNotContains(
            match_page, f'href="{self._url("changelist", model="match")}"'
        )

        result_page = self.client.get(result_url)
        slots = list(
            match.slots.select_related("resolved_entry__entrant").order_by("position")
        )
        for field, slot in zip(
            ("side_one_score", "side_two_score"), slots, strict=True
        ):
            self.assertIn(
                slot.resolved_entry.entrant.display_name,
                result_page.context["form"].fields[field].label,
            )
        choices = list(result_page.context["form"].fields["winner_position"].choices)
        self.assertEqual(choices[0][0], "")
        self.assertEqual(
            choices[1:],
            [
                (slot.position, slot.resolved_entry.entrant.display_name)
                for slot in slots
            ],
        )
        response = self.client.post(
            result_url,
            {
                "expected_revision": competition.revision,
                "outcome": Match.Outcome.PLAYED,
                "side_one_score": 2,
                "side_two_score": 0,
                "winner_position": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        match.refresh_from_db()
        self.assertEqual(match.winner_id, slots[0].resolved_entry_id)
        destination = match.dependent_slots.get()
        self.assertEqual(destination.resolved_entry_id, match.winner_id)
        self.assertNotContains(
            self.client.get(self._url("change", competition)), result_url
        )

    def test_setup_offers_elimination_formats_and_requires_double_final_policy(self):
        self.client.post(self._url("add"), {"tournament_game": self.division.pk})
        competition = Competition.objects.get(tournament_game=self.division)
        url = self._url("configure_detail", competition)
        response = self.client.get(url)
        self.assertEqual(
            list(response.context["form"].fields["format"].choices),
            [
                (Stage.Format.SINGLE_ELIMINATION, "Single elimination"),
                (Stage.Format.DOUBLE_ELIMINATION, "Double elimination"),
                (Stage.Format.ROUND_ROBIN, "Round robin"),
                (Stage.Format.SWISS_FIXED, "Fixed Swiss"),
                (Stage.Format.SWISS_THRESHOLD, "Threshold Swiss"),
            ],
        )
        self.assertEqual(
            list(response.context["form"].fields["grand_final_policy"].choices),
            [
                ("", "Choose a grand final policy"),
                (Stage.GrandFinalPolicy.RESET, "Reset"),
                (Stage.GrandFinalPolicy.NO_RESET, "No reset"),
            ],
        )

        response = self.client.post(
            url,
            {
                "expected_revision": competition.revision,
                "name": "Double elimination playoffs",
                "format": Stage.Format.DOUBLE_ELIMINATION,
                "grand_final_policy": "",
                "default_series_length": 3,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "grand_final_policy",
            "Choose reset or no reset.",
        )
        self.assertFalse(competition.stages.exists())

    def test_reset_policy_workspace_has_section_headings_and_source_outcomes(self):
        competition, draw, preview, publication = self._publish_double_workspace(
            Stage.GrandFinalPolicy.RESET
        )
        for heading in (
            "Upper bracket round 1",
            "Upper bracket final",
            "Lower bracket round 1",
            "Lower bracket final",
            "Grand final",
            "Reset final",
        ):
            self.assertContains(preview, heading)
        self.assertContains(preview, "Winner of")
        self.assertContains(preview, "Loser of")
        self.assertContains(preview, "Grand final policy")
        self.assertContains(preview, "Reset if necessary")
        self.assertContains(publication, "Reset if necessary")

        published = self.client.get(self._url("change", competition))
        self.assertContains(published, "Reset if necessary")
        reset = Match.objects.get(
            round__draw=draw,
            round__section="FINALS",
            round__number=2,
        )
        self.assertEqual(reset.status, Match.Status.CONDITIONAL)
        self.assertContains(published, "Reserved final")
        self.assertContains(published, "activates if the lower-bracket winner wins")
        self.assertNotContains(published, self._url("finalize_detail", reset, "match"))

    def test_no_reset_policy_reaches_publication_without_reserved_final(self):
        competition, draw, preview, publication = self._publish_double_workspace(
            Stage.GrandFinalPolicy.NO_RESET
        )
        self.assertContains(preview, "No reset")
        self.assertContains(publication, "No reset")
        self.assertContains(
            self.client.get(self._url("change", competition)), "No reset"
        )
        self.assertFalse(
            Match.objects.filter(
                round__draw=draw,
                round__section="FINALS",
                round__number=2,
            ).exists()
        )

    def test_workspace_connectors_keep_match_sources_after_publication(self):
        competition, draw, preview, _ = self._publish_double_workspace(
            Stage.GrandFinalPolicy.RESET
        )
        for response in (preview, self.client.get(self._url("change", competition))):
            self.assertContains(response, "competitions/bracket.js")
            for match in Match.objects.filter(round__draw=draw).prefetch_related(
                "slots"
            ):
                self.assertContains(response, f'data-match-id="{match.pk}"')
                card = match_card(match, self.organizer)
                self.assertEqual(
                    [
                        (
                            slot["position"],
                            slot["source_match_id"],
                            slot["source_outcome"],
                        )
                        for slot in card["slots"]
                    ],
                    [
                        (slot.position, slot.source_match_id, slot.source_outcome)
                        for slot in match.slots.all()
                    ],
                )
                for slot in match.slots.all():
                    if slot.source_match_id:
                        self.assertContains(
                            response,
                            f'data-source-match="{slot.source_match_id}" '
                            f'data-source-outcome="{slot.source_outcome}"',
                        )

    def test_large_double_workspace_groups_every_match_in_ordered_sections(self):
        self.registrations = list(self.registrations)
        for index in range(4, 17):
            registration = Registration.objects.create(
                tournament_game=self.division,
                status=Registration.Status.APPROVED,
                fee_amount_snapshot="0.00",
                fee_currency_snapshot="VND",
            )
            RegistrationMember.objects.create(
                registration=registration,
                gamer_tag_snapshot=f"Bracket Player {index}",
                is_captain=True,
                display_order=1,
            )
            self.registrations.append(registration)
        competition, draw, preview, _ = self._publish_double_workspace(
            Stage.GrandFinalPolicy.RESET, entrant_count=16
        )
        for response in (preview, self.client.get(self._url("change", competition))):
            sections = response.context.get("bracket_sections", [])
            self.assertEqual(
                [section["kind"] for section in sections], ["UPPER", "LOWER", "FINALS"]
            )
            self.assertEqual(
                [len(section["rounds"]) for section in sections], [4, 6, 2]
            )
            self.assertCountEqual(
                [
                    match["id"]
                    for section in sections
                    for round_ in section["rounds"]
                    for match in round_["matches"]
                ],
                Match.objects.filter(round__draw=draw).values_list("pk", flat=True),
            )

    def test_two_entrant_double_workspace_has_no_empty_lower_section(self):
        _, _, preview, _ = self._publish_double_workspace(
            Stage.GrandFinalPolicy.NO_RESET, entrant_count=2
        )
        self.assertEqual(
            [
                section["kind"]
                for section in preview.context.get("bracket_sections", [])
            ],
            ["UPPER", "FINALS"],
        )

    def test_reserved_final_allows_setup_actions_but_rejects_play_actions(self):
        competition, draw, _, _ = self._publish_double_workspace(
            Stage.GrandFinalPolicy.RESET
        )
        reset = Match.objects.get(
            round__draw=draw,
            round__section="FINALS",
            round__number=2,
        )
        urls = {
            action: self._url(action, reset, "match")
            for action in (
                "schedule_detail",
                "series_detail",
                "start_detail",
                "progress_detail",
                "finalize_detail",
            )
        }
        before = (
            competition.revision,
            competition.changes.count(),
            reset.status,
            reset.scheduled_at,
            reset.series_length_override,
        )
        detail = self.client.get(self._url("change", reset, "match"))
        self.assertContains(detail, urls["schedule_detail"])
        self.assertContains(detail, urls["series_detail"])
        for action in ("start_detail", "progress_detail", "finalize_detail"):
            self.assertNotContains(detail, urls[action])
        for url in urls.values():
            self.assertEqual(self.client.get(url).status_code, 200)
        competition.refresh_from_db()
        reset.refresh_from_db()
        self.assertEqual(
            (
                competition.revision,
                competition.changes.count(),
                reset.status,
                reset.scheduled_at,
                reset.series_length_override,
            ),
            before,
        )

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.organizer)
        csrf_client.get(urls["schedule_detail"])
        self.assertEqual(
            csrf_client.post(
                urls["schedule_detail"],
                {
                    "expected_revision": competition.revision,
                    "scheduled_at": "2026-10-01T10:00",
                },
            ).status_code,
            403,
        )

        stale_revision = competition.revision
        response = self.client.post(
            urls["schedule_detail"],
            {
                "expected_revision": stale_revision,
                "scheduled_at": "2026-10-01T10:00",
            },
        )
        self.assertEqual(response.status_code, 302)
        competition.refresh_from_db()
        reset.refresh_from_db()
        self.assertIsNotNone(reset.scheduled_at)
        self.assertEqual(reset.status, Match.Status.CONDITIONAL)

        stale_response = self.client.post(
            urls["series_detail"],
            {"expected_revision": stale_revision, "series_length": 5},
        )
        self.assertEqual(stale_response.status_code, 200)
        self.assertContains(stale_response, "Competition changed from revision")
        reset.refresh_from_db()
        self.assertIsNone(reset.series_length_override)

        response = self.client.post(
            urls["series_detail"],
            {"expected_revision": competition.revision, "series_length": 5},
        )
        self.assertEqual(response.status_code, 302)
        reset.refresh_from_db()
        self.assertEqual(reset.series_length_override, 5)

        invalid_posts = {
            "start_detail": ({}, "Only a pending match can start"),
            "progress_detail": (
                {"side_one_score": 0, "side_two_score": 0},
                "inactive reset final",
            ),
            "finalize_detail": (
                {
                    "outcome": Match.Outcome.FORFEIT,
                    "winner_position": 1,
                },
                "inactive reset final",
            ),
        }
        for action, (data, error) in invalid_posts.items():
            with self.subTest(action=action):
                competition.refresh_from_db()
                revision = competition.revision
                response = self.client.post(
                    urls[action], {"expected_revision": revision, **data}
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)
                competition.refresh_from_db()
                reset.refresh_from_db()
                self.assertEqual(competition.revision, revision)
                self.assertEqual(reset.status, Match.Status.CONDITIONAL)

        self._grant_viewer("view_competition", "view_match")
        for action in ("schedule_detail", "series_detail", "start_detail"):
            with self.subTest(permission_action=action):
                self.assertEqual(self.client.get(urls[action]).status_code, 403)
                self.assertEqual(self.client.post(urls[action], {}).status_code, 403)

    def test_correction_displays_reserved_final_activation_and_private_reason(self):
        competition, draw, _, _ = self._publish_double_workspace(
            Stage.GrandFinalPolicy.RESET, entrant_count=2
        )
        upper = Match.objects.get(
            round__draw=draw, round__section="UPPER", round__number=1
        )
        finalize_match(
            actor=self.organizer,
            match_id=upper.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.FORFEIT,
            winner_position=1,
        )
        competition.refresh_from_db()
        final = Match.objects.get(
            round__draw=draw, round__section="FINALS", round__number=1
        )
        finalize_match(
            actor=self.organizer,
            match_id=final.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.FORFEIT,
            winner_position=1,
        )
        competition.refresh_from_db()
        reset = Match.objects.get(
            round__draw=draw, round__section="FINALS", round__number=2
        )
        self.assertEqual(reset.status, Match.Status.NOT_REQUIRED)
        finalize_url = self._url("finalize_detail", reset, "match")
        workspace = self.client.get(self._url("change", competition))
        self.assertNotContains(workspace, finalize_url)

        correct_url = self._url("correct_detail", final, "match")
        response = self.client.post(
            correct_url,
            {
                "expected_revision": competition.revision,
                "outcome": Match.Outcome.FORFEIT,
                "winner_position": 2,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reserved final activation changes")
        self.assertContains(response, reset.code)
        self.assertContains(response, "Not required")
        self.assertContains(response, "Active")
        self.assertContains(response, "No other match results need to be cleared")

        reason = "Grand final winner was recorded on the wrong side."
        response = self.client.post(
            correct_url,
            {"token": response.context["token"], "internal_reason": reason},
        )
        self.assertEqual(response.status_code, 302)
        reset.refresh_from_db()
        self.assertEqual(reset.status, Match.Status.PENDING)
        changes = self.client.get(self._url("change", competition), {"tab": "changes"})
        self.assertContains(changes, "Reserved final activation changes")
        self.assertContains(changes, reset.code)
        self.assertContains(changes, "Not required")
        self.assertContains(changes, "Active")
        self.assertContains(changes, reason)

    def test_draft_bye_and_unresolved_matches_have_no_result_action(self):
        competition, draw = self._draft()
        workspace_url = self._url("change", competition)
        response = self.client.get(workspace_url)
        for match in Match.objects.filter(round__draw=draw):
            self.assertNotContains(
                response, self._url("finalize_detail", match, "match")
            )
        publish_draw(
            actor=self.organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
        )
        response = self.client.get(workspace_url)
        for match in Match.objects.filter(round__draw=draw):
            result_url = self._url("finalize_detail", match, "match")
            if match.outcome == Match.Outcome.BYE or match.round.number == 2:
                self.assertNotContains(response, result_url)
                self.assertNotContains(
                    self.client.get(self._url("change", match, "match")), result_url
                )
            else:
                self.assertContains(response, result_url)

    def test_viewers_cannot_see_or_call_mutation_actions(self):
        competition, draw = self._draft(published=True)
        self._grant_viewer("view_competition", "view_match")
        response = self.client.get(self._url("change", competition))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["primary_action"])
        match = Match.objects.get(
            round__draw=draw, round__number=1, status=Match.Status.PENDING
        )
        actions = [
            self._url(action, competition)
            for action in (
                "configure_detail",
                "entrants_detail",
                "draw_detail",
                "publish_detail",
            )
        ] + [
            self._url(action, match, "match")
            for action in (
                "schedule_detail",
                "series_detail",
                "start_detail",
                "progress_detail",
                "finalize_detail",
                "correct_detail",
            )
        ]
        for url in actions:
            with self.subTest(url=url):
                self.assertNotContains(response, url)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)
        detail = self.client.get(self._url("change", match, "match"))
        self.assertEqual(detail.status_code, 200)
        for action in ("schedule_detail", "finalize_detail", "correct_detail"):
            self.assertNotContains(detail, self._url(action, match, "match"))
        self.assertEqual(self.client.get(self._url("add")).status_code, 403)

    def test_changes_requires_its_own_view_permission(self):
        competition, _ = self._draft(published=True)
        secret = "PRIVATE correction investigation"
        competition.changes.filter(revision=competition.revision).update(
            internal_reason=secret
        )
        workspace_url = self._url("change", competition)
        self._grant_viewer("view_competition", "change_competition", "change_changeset")
        response = self.client.get(workspace_url)
        self.assertNotContains(response, "?tab=changes")
        self.assertNotContains(response, secret)
        self.assertEqual(
            self.client.get(workspace_url, {"tab": "changes"}).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                self._url("change", competition.changes.first(), "changeset")
            ).status_code,
            403,
        )

        self._grant_viewer("view_competition", "view_changeset")
        response = self.client.get(workspace_url, {"tab": "changes"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, secret)
        self.assertFalse(response.context["primary_action"])
        public_response = Client().get(
            reverse("public-competition-changes", args=[self.division.pk])
        )
        self.assertEqual(public_response.status_code, 200)
        self.assertNotContains(public_response, secret)
        self.assertNotContains(public_response, self.organizer.email)

    def test_scorekeeper_can_enter_results_without_competition_setup_permission(self):
        competition, draw = self._draft(published=True)
        self._grant_viewer("view_competition", "change_match")
        match = Match.objects.get(
            round__draw=draw, round__number=1, status=Match.Status.PENDING
        )
        result_url = self._url("finalize_detail", match, "match")
        self._primary_action(competition, result_url)
        response = self.client.get(self._url("change", competition))
        self.assertNotContains(response, self._url("configure_detail", competition))
        self.assertNotContains(response, "?tab=changes")
        self.assertEqual(self.client.get(result_url).status_code, 200)
        response = self.client.post(
            result_url,
            {
                "expected_revision": competition.revision,
                "outcome": Match.Outcome.FORFEIT,
                "winner_position": 2,
            },
        )
        self.assertEqual(response.status_code, 302)
        match.refresh_from_db()
        self.assertEqual(match.winner_id, match.slots.get(position=2).resolved_entry_id)
        correction_url = self._url("correct_detail", match, "match")
        self.assertNotContains(
            self.client.get(self._url("change", competition)), correction_url
        )
        self.assertEqual(self.client.get(correction_url).status_code, 403)
        self.assertEqual(self.client.post(correction_url, {}).status_code, 403)

    def test_saved_seeds_are_preserved_and_randomize_accepts_no_manual_values(self):
        competition, _ = self._draft()
        order = list(competition.entrants.order_by("-pk").values_list("pk", flat=True))
        save_elimination_draw(
            actor=self.organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            entrant_order=order,
        )
        competition.refresh_from_db()
        response = self.client.get(self._url("draw_detail", competition))
        self.assertEqual(
            [
                int(response.context["form"][f"seed_{number}"].value())
                for number in range(1, 4)
            ],
            order,
        )
        self._submit(
            competition,
            "draw_detail",
            {"randomize": "on", "seed_1": "", "seed_2": "", "seed_3": ""},
        )
        current_draw = StageDraw.objects.get(
            stage__competition=competition, state=StageDraw.State.DRAFT
        )
        self.assertTrue(current_draw.randomized)
        self.assertCountEqual(
            current_draw.entries.values_list("entrant_id", flat=True), order
        )

    def test_team_selection_uses_team_names_and_tag_fallback(self):
        self.division.main_roster_size = 5
        self.division.save(update_fields=("main_roster_size",))
        self.registrations[0].team_name = "USEC Phoenix"
        self.registrations[0].save(update_fields=("team_name",))
        self.registrations[1].team_tag = "LOTUS"
        self.registrations[1].save(update_fields=("team_tag",))
        competition = create_competition(
            actor=self.organizer, tournament_game_id=self.division.pk
        )
        response = self.client.get(self._url("entrants_detail", competition))
        choices = {
            value.value: label
            for value, label in response.context["form"].fields["registrations"].choices
        }
        self.assertEqual(choices[self.registrations[0].pk], "USEC Phoenix")
        self.assertEqual(choices[self.registrations[1].pk], "LOTUS")

    def test_gets_do_not_mutate_and_result_post_requires_csrf(self):
        competition, draw = self._draft(published=True)
        match = Match.objects.get(
            round__draw=draw, round__number=1, status=Match.Status.PENDING
        )
        counts = (
            competition.revision,
            competition.changes.count(),
            Match.objects.count(),
        )
        for tab in ("setup", "entrants", "bracket", "changes"):
            self.assertEqual(
                self.client.get(
                    self._url("change", competition), {"tab": tab}
                ).status_code,
                200,
            )
        result_url = self._url("finalize_detail", match, "match")
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.organizer)
        self.assertEqual(csrf_client.get(result_url).status_code, 200)
        self.assertEqual(
            csrf_client.post(
                result_url, {"expected_revision": competition.revision}
            ).status_code,
            403,
        )
        competition.refresh_from_db()
        self.assertEqual(
            (competition.revision, competition.changes.count(), Match.objects.count()),
            counts,
        )

    def test_new_competition_get_is_read_only_and_post_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.organizer)
        url = self._url("add")
        response = csrf_client.get(url)
        self.assertContains(response, "Workspace Cup")
        self.assertContains(response, 'name="tournament_game"')
        self.assertFalse(Competition.objects.exists())
        self.assertEqual(
            csrf_client.post(url, {"tournament_game": self.division.pk}).status_code,
            403,
        )
        response = csrf_client.post(
            url,
            {
                "tournament_game": self.division.pk,
                "csrfmiddlewaretoken": csrf_client.cookies["csrftoken"].value,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Competition.objects.get().tournament_game_id, self.division.pk)
        self.assertEqual(Tournament.objects.count(), 1)

    def test_existing_division_create_confirmation_names_the_division(self):
        response = self.client.get(
            reverse(
                "admin:competitions_competition_create_for_division",
                args=[self.division.pk],
            )
        )
        self.assertContains(response, "Workspace Cup")
        self.assertContains(response, "Chess")
        self.assertFalse(Competition.objects.exists())
