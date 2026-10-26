from datetime import timedelta
from decimal import Decimal
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Institution
from competitions.models import Competition, Match, Round, Stage, StageDraw
from registrations.models import (
    PaymentAttempt,
    PaymentIntent,
    PaymentSettings,
    Registration,
    RegistrationStatusEvent,
)
from tournaments.models import Game, Tournament, TournamentGame


@override_settings(DEBUG=True)
class SeedDevDataCommandTests(TestCase):
    def test_lifecycle_seed_retains_ids_results_and_private_history(self):
        from competitions.models import ChangeSet

        self.run_seed()
        competitions = Competition.objects.filter(
            tournament_game__tournament__slug="dev-usec-lifecycle"
        ).order_by("tournament_game__game__slug")
        self.assertEqual(competitions.count(), 3)
        self.assertEqual(
            [c.ended_at is not None for c in competitions], [True, False, False]
        )
        matches = Match.objects.filter(round__draw__stage__competition__in=competitions)
        snapshot = list(matches.order_by("pk").values())
        history = list(
            ChangeSet.objects.filter(competition__in=competitions)
            .order_by("pk")
            .values()
        )
        self.assertTrue(
            matches.filter(round__draw__state="SUPERSEDED", outcome="PLAYED").exists()
        )
        removed = competitions.get(tournament_game__game__slug="lifecycle-removal")
        self.assertTrue(
            removed.entrants.filter(
                status="WITHDRAWN", removal_change__isnull=False
            ).exists()
        )
        reopened = competitions.get(tournament_game__game__slug="lifecycle-reopened")
        self.assertFalse(
            reopened.stages.get(sequence=2).draws.filter(state="PUBLISHED").exists()
        )
        client = APIClient()
        for competition in competitions:
            response = client.get(
                f"/api/tournament-games/{competition.tournament_game_id}/competition/"
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("PRIVATE-LIFECYCLE", str(response.data))
            self.assertNotIn("@example.invalid", str(response.data))
            changes = client.get(
                f"/api/tournament-games/{competition.tournament_game_id}/competition/changes/"
            )
            self.assertEqual(changes.status_code, 200)
            self.assertNotIn("PRIVATE-LIFECYCLE", str(changes.data))
            self.assertNotIn("internal_reason", str(changes.data))
            self.assertNotIn("private_data", str(changes.data))
        self.assertTrue(
            any("PRIVATE-LIFECYCLE" in event["internal_reason"] for event in history)
        )
        self.run_seed()
        self.assertEqual(list(matches.order_by("pk").values()), snapshot)
        self.assertEqual(
            list(
                ChangeSet.objects.filter(competition__in=competitions)
                .order_by("pk")
                .values()
            ),
            history,
        )

    def test_seed_preserves_existing_payment_configuration_on_reruns(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                PaymentSettings.objects.update_or_create(
                    pk=1,
                    defaults={
                        "enabled": enabled,
                        "bank_name": "Operator bank",
                        "bank_bin": "970436",
                        "account_number": "987654321",
                        "account_holder": "OPERATOR HOLDER",
                        "payment_hold_minutes": 125,
                    },
                )
                before = PaymentSettings.objects.values().get(pk=1)
                self.run_seed()
                self.run_seed()
                self.assertEqual(PaymentSettings.objects.values().get(pk=1), before)
                self.assertTrue(
                    all(
                        intent.account_holder_snapshot
                        == "DEVELOPMENT SAMPLE DO NOT PAY"
                        for intent in PaymentIntent.objects.all()
                    )
                )

    def test_seed_failure_rolls_back_temporary_payment_configuration(self):
        PaymentSettings.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": False,
                "bank_name": "Operator bank",
                "payment_hold_minutes": 125,
            },
        )
        before = PaymentSettings.objects.values().get(pk=1)
        with patch(
            "registrations.dev_seed._rebuild_registrations",
            side_effect=ValidationError("fixture failure"),
        ):
            with self.assertRaisesMessage(CommandError, "fixture failure"):
                self.run_seed()
        self.assertEqual(PaymentSettings.objects.values().get(pk=1), before)

    def test_seed_does_not_leave_fake_receiving_settings_enabled(self):
        PaymentSettings.objects.all().delete()
        self.run_seed()
        self.assertFalse(PaymentSettings.objects.exists())

    def test_rerun_removes_replaced_sample_images_after_commit(self):
        self.run_seed()
        previous = [
            attempt.proof_file
            for attempt in PaymentAttempt.objects.filter(
                registration__submitted_by__email="player@email.com"
            )
        ]
        self.assertTrue(all(proof.storage.exists(proof.name) for proof in previous))
        with self.captureOnCommitCallbacks(execute=True):
            self.run_seed()
        self.assertTrue(all(not proof.storage.exists(proof.name) for proof in previous))
        self.assertTrue(
            all(
                attempt.proof_file.storage.exists(attempt.proof_file.name)
                for attempt in PaymentAttempt.objects.filter(
                    registration__submitted_by__email="player@email.com"
                )
            )
        )

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

    def run_seed(self, **options) -> str:
        output = StringIO()
        call_command("seed_dev_data", stdout=output, **options)
        return output.getvalue()

    @override_settings(DEBUG=False)
    def test_command_requires_explicit_non_debug_override(self):
        with self.assertRaisesMessage(
            CommandError,
            "seed_dev_data creates predictable credentials",
        ):
            self.run_seed()

        self.assertFalse(
            get_user_model().objects.filter(email="player@email.com").exists()
        )

        self.run_seed(allow_non_debug=True)

        self.assertTrue(
            get_user_model().objects.filter(email="player@email.com").exists()
        )

    def test_command_creates_documented_accounts_and_permissions(self):
        output = self.run_seed()
        user_model = get_user_model()

        player = user_model.objects.get(email="player@email.com")
        organizer = user_model.objects.get(email="organizer@email.com")
        admin = user_model.objects.get(email="admin@email.com")

        self.assertTrue(player.check_password("player@123"))
        self.assertEqual(player.first_name, "Development")
        self.assertEqual(player.last_name, "Player")
        self.assertEqual(
            player.institution.label,
            "TRƯỜNG ĐẠI HỌC KHOA HỌC TỰ NHIÊN (ĐẠI HỌC QUỐC GIA TP. HỒ CHÍ MINH)",
        )
        self.assertEqual(player.institution.short_name, "HCMUS")
        self.assertEqual(player.institution.english_name, "University of Science - VNU")
        self.assertEqual(player.institution.source, Institution.Source.CATALOGUE)
        self.assertEqual(
            Institution.objects.filter(
                source=Institution.Source.CATALOGUE,
                value="222",
            ).count(),
            1,
        )
        self.assertFalse(hasattr(player, "gamer_tag"))
        self.assertTrue(player.is_active)
        self.assertFalse(player.is_staff)
        self.assertFalse(player.is_superuser)
        self.assertFalse(player.groups.exists())
        self.assertEqual(player.student_id, "")
        player.full_clean()

        self.assertTrue(organizer.check_password("organizer@123"))
        self.assertTrue(organizer.is_active)
        self.assertTrue(organizer.is_staff)
        self.assertFalse(organizer.is_superuser)
        self.assertIsNone(organizer.institution)
        self.assertSetEqual(
            set(organizer.groups.values_list("name", flat=True)),
            {"Organizers"},
        )
        self.assertTrue(organizer.has_perm("registrations.change_registration"))
        self.assertTrue(organizer.has_perm("registrations.change_paymentattempt"))
        self.assertFalse(organizer.has_perm("registrations.delete_registration"))
        self.assertTrue(organizer.student_id)
        organizer.full_clean()

        self.assertTrue(admin.check_password("admin@123"))
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertIsNone(admin.institution)
        self.assertFalse(admin.groups.exists())
        self.assertTrue(admin.student_id)
        admin.full_clean()

        self.assertEqual(Group.objects.filter(name="Organizers").count(), 1)
        self.assertIn("Player: player@email.com / player@123", output)
        self.assertIn("Organizer: organizer@email.com / organizer@123", output)
        self.assertIn("Admin: admin@email.com / admin@123", output)

    def test_command_seeds_public_availability_and_hides_draft(self):
        self.run_seed()
        client = APIClient()

        list_response = client.get("/api/tournaments/")
        self.assertEqual(list_response.status_code, 200)
        self.assertSetEqual(
            {item["slug"] for item in list_response.data},
            {
                "dev-usec-current",
                "dev-usec-archive",
                "dev-usec-double-elimination",
                "dev-usec-round-robin",
                "dev-usec-multi-stage",
                "dev-usec-swiss",
                "dev-usec-lifecycle",
                "dev-fpt-shop-uni-tour-2026",
                "dev-sponsor-open",
                "dev-sponsor-arena",
                "dev-sponsor-expired",
            },
        )

        current_response = client.get("/api/tournaments/dev-usec-current/")
        self.assertEqual(current_response.status_code, 200)
        current_states = {
            game["game_slug"]: game["registration_state"]
            for game in current_response.data["tournament_games"]
        }
        self.assertEqual(
            current_states,
            {
                "valorant": "open",
                "chess": "open",
                "counter-strike-2": "full",
                "league-of-legends": "not_open",
            },
        )

        archive_response = client.get("/api/tournaments/dev-usec-archive/")
        self.assertEqual(archive_response.status_code, 200)
        self.assertEqual(
            archive_response.data["tournament_games"][0]["registration_state"],
            "closed",
        )

        draft_response = client.get("/api/tournaments/dev-usec-draft/")
        self.assertEqual(draft_response.status_code, 404)
        self.assertFalse(Tournament.objects.get(slug="dev-usec-draft").is_published)

    def test_command_seeds_sponsor_bracket_fixtures(self):
        output = self.run_seed()
        now = timezone.now()
        tournaments = {
            tournament.slug: tournament
            for tournament in Tournament.objects.filter(slug__startswith="dev-sponsor-")
        }

        self.assertSetEqual(
            set(tournaments),
            {"dev-sponsor-open", "dev-sponsor-arena", "dev-sponsor-expired"},
        )
        self.assertEqual(
            TournamentGame.objects.get(
                tournament__slug="dev-sponsor-open", game__slug="valorant"
            ).fee_amount,
            Decimal("50000.00"),
        )
        self.assertEqual(
            TournamentGame.objects.get(
                tournament__slug="dev-sponsor-open",
                game__slug="league-of-legends",
            ).fee_amount,
            Decimal("100000.00"),
        )
        self.assertEqual(
            TournamentGame.objects.get(
                tournament__slug="dev-sponsor-arena", game__slug="arena-of-valor"
            ).fee_amount,
            Decimal("0.00"),
        )

        expired_divisions = TournamentGame.objects.filter(
            tournament__slug__in=("dev-sponsor-open", "dev-sponsor-expired")
        ).exclude(game__slug="league-of-legends")
        self.assertTrue(
            all(division.registration_closes_at < now for division in expired_divisions)
        )
        self.assertTrue(
            TournamentGame.objects.filter(
                tournament__slug="dev-sponsor-expired",
                registration_closes_at__lt=now,
            ).count()
            >= 2
        )

        for tournament in tournaments.values():
            self.assertGreaterEqual(
                Registration.objects.filter(
                    tournament_game__tournament=tournament,
                    status=Registration.Status.APPROVED,
                ).count(),
                8,
            )
        for division in TournamentGame.objects.filter(
            tournament__slug__startswith="dev-sponsor-"
        ):
            self.assertEqual(
                Registration.objects.filter(
                    tournament_game=division,
                    status=Registration.Status.APPROVED,
                ).count(),
                8,
            )
        self.assertEqual(
            PaymentAttempt.objects.filter(
                registration__tournament_game__tournament__slug__startswith="dev-sponsor-",
                status=PaymentAttempt.Status.VERIFIED,
            ).count(),
            32,
        )
        self.assertFalse(
            PaymentAttempt.objects.filter(
                registration__tournament_game__tournament__slug="dev-sponsor-arena"
            ).exists()
        )

        competition = Competition.objects.get(
            tournament_game__tournament__slug="dev-sponsor-open",
            tournament_game__game__slug="league-of-legends",
        )
        draw = competition.stages.get().draws.get(state=StageDraw.State.PUBLISHED)
        self.assertEqual(competition.entrants.count(), 8)
        self.assertEqual(draw.entries.count(), 8)
        self.assertEqual(Match.objects.filter(round__draw=draw).count(), 7)
        self.assertIn(
            "League of Legends: published eight-team single-elimination bracket",
            output,
        )

    def test_fpt_shop_uni_tour_fixture_matches_workbook_bracket_shape(self):
        output = self.run_seed()
        self.run_seed()
        tournament = Tournament.objects.get(slug="dev-fpt-shop-uni-tour-2026")
        division = TournamentGame.objects.get(
            tournament=tournament,
            game__slug="arena-of-valor",
        )
        registrations = list(
            Registration.objects.filter(tournament_game=division).order_by("team_tag")
        )
        competition = Competition.objects.get(tournament_game=division)
        stage = competition.stages.get()
        draw = stage.draws.get(state=StageDraw.State.PUBLISHED)
        rounds = list(draw.rounds.order_by("number"))
        matches = Match.objects.filter(round__draw=draw)

        self.assertTrue(tournament.is_published)
        self.assertIn("Development Fixture", tournament.name)
        self.assertEqual(division.main_roster_size, 5)
        self.assertEqual(division.registration_capacity, 16)
        self.assertEqual(division.fee_amount, Decimal("0.00"))
        self.assertEqual(len(registrations), 16)
        self.assertTrue(
            all(
                registration.status == Registration.Status.APPROVED
                for registration in registrations
            )
        )
        self.assertTrue(
            all(
                registration.contact_email_snapshot.endswith("@example.invalid")
                for registration in registrations
            )
        )
        self.assertTrue(
            all(
                registration.team_name.startswith("Arena of Valor Team ")
                for registration in registrations
            )
        )
        self.assertEqual(competition.entrants.count(), 16)
        self.assertEqual([round_.matches.count() for round_ in rounds], [8, 4, 2, 1])
        self.assertEqual(stage.format, Stage.Format.SINGLE_ELIMINATION)
        self.assertEqual(stage.default_series_length, 1)
        self.assertEqual(
            [round_.series_length_override for round_ in rounds],
            [None, None, 3, 3],
        )
        self.assertEqual(matches.count(), 15)
        self.assertFalse(matches.exclude(status=Match.Status.PENDING).exists())
        self.assertEqual(matches.filter(scheduled_at__isnull=False).count(), 1)
        self.assertIn(
            "FPT Shop Uni Tour 2026: synthetic 16-team LQM bracket",
            output,
        )

    def test_command_seeds_one_rerunnable_published_bracket(self):
        output = self.run_seed()
        self.run_seed()
        competition = Competition.objects.get(
            tournament_game__tournament__slug="dev-usec-current",
            tournament_game__game__slug="chess",
        )
        draw = competition.stages.get().draws.get(state=StageDraw.State.PUBLISHED)

        self.assertEqual(competition.entrants.count(), 5)
        self.assertEqual(draw.entries.count(), 5)
        self.assertEqual(Match.objects.filter(round__draw=draw).count(), 7)
        self.assertEqual(
            Competition.objects.filter(
                tournament_game=competition.tournament_game
            ).count(),
            1,
        )
        self.assertIn("Chess: published five-player single-elimination bracket", output)

        response = APIClient().get(
            f"/api/tournament-games/{competition.tournament_game_id}/competition/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["stages"][0]["entries"]), 5)

    def test_double_elimination_fixtures_are_published_valid_and_stable(self):
        self.run_seed()
        competitions = Competition.objects.filter(
            tournament_game__tournament__slug="dev-usec-double-elimination"
        ).order_by("tournament_game__game__slug")
        self.assertEqual(competitions.count(), 2)
        original_ids = list(competitions.values_list("pk", flat=True))
        original_matches = list(
            Match.objects.filter(round__draw__stage__competition__in=competitions)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        self.run_seed()
        self.assertEqual(list(competitions.values_list("pk", flat=True)), original_ids)
        self.assertEqual(
            list(
                Match.objects.filter(round__draw__stage__competition__in=competitions)
                .order_by("pk")
                .values_list("pk", flat=True)
            ),
            original_matches,
        )
        for competition in competitions:
            stage = competition.stages.get()
            draw = stage.draws.get(state=StageDraw.State.PUBLISHED)
            reset = stage.grand_final_policy == Stage.GrandFinalPolicy.RESET
            self.assertEqual(stage.format, Stage.Format.DOUBLE_ELIMINATION)
            self.assertEqual(draw.entries.count(), 16 if reset else 5)
            self.assertEqual(
                stage.status, Stage.Status.READY if reset else Stage.Status.COMPLETE
            )
            self.assertEqual(stage.grand_final_policy, "RESET" if reset else "NO_RESET")
            for entrant in competition.entrants.select_related("registration"):
                registration = entrant.registration
                self.assertEqual(registration.status, Registration.Status.APPROVED)
                self.assertEqual(registration.members.count(), 5)
                self.assertTrue(
                    registration.contact_email_snapshot.endswith("@example.invalid")
                )
                self.assertEqual(registration.fee_amount_snapshot, Decimal("0.00"))
            matches = Match.objects.filter(round__draw=draw)
            if reset:
                self.assertEqual(stage.default_series_length, 1)
                self.assertEqual(matches.count(), 31)
                self.assertEqual(
                    matches.filter(status=Match.Status.CONDITIONAL).count(), 1
                )
                self.assertSetEqual(
                    set(
                        draw.rounds.filter(series_length_override=3).values_list(
                            "section", "number"
                        )
                    ),
                    {
                        (Round.Section.UPPER, 3),
                        (Round.Section.UPPER, 4),
                        (Round.Section.LOWER, 6),
                        (Round.Section.FINALS, 1),
                        (Round.Section.FINALS, 2),
                    },
                )
            else:
                self.assertEqual(matches.count(), 14)
                self.assertTrue(matches.filter(outcome=Match.Outcome.BYE).exists())
                self.assertFalse(matches.exclude(status=Match.Status.FINAL).exists())
                self.assertIsNotNone(stage.champion_id)
            response = APIClient().get(
                f"/api/tournament-games/{competition.tournament_game_id}/competition/"
            )
            self.assertEqual(response.status_code, 200)
            self.assertSetEqual(
                {round_["section"] for round_ in response.data["stages"][0]["rounds"]},
                {"UPPER", "LOWER", "FINALS"},
            )
            self.assertNotIn("@example.invalid", str(response.data))

    def test_command_seeds_registration_status_payment_and_timeline_matrix(self):
        output = self.run_seed()
        player = get_user_model().objects.get(email="player@email.com")
        registrations = {
            registration.tournament_game.game.slug: registration
            for registration in Registration.objects.filter(submitted_by=player)
            .select_related("tournament_game__game", "tournament_game__tournament")
            .prefetch_related("payment_attempts", "status_events")
        }

        self.assertSetEqual(
            set(registrations),
            {"valorant", "chess", "counter-strike-2", "rocket-league"},
        )
        self.assertIn("Valorant: SUBMITTED / payment PENDING", output)
        self.assertIn("Development draft: unpublished", output)
        self.assertEqual(
            registrations["valorant"].status,
            Registration.Status.SUBMITTED,
        )
        self.assertEqual(
            registrations["chess"].status,
            Registration.Status.APPROVED,
        )
        self.assertEqual(
            registrations["counter-strike-2"].status,
            Registration.Status.UNDER_REVIEW,
        )
        self.assertEqual(
            registrations["rocket-league"].status,
            Registration.Status.REJECTED,
        )

        payment_statuses = {
            slug: list(
                registration.payment_attempts.order_by("created_at", "pk").values_list(
                    "status", flat=True
                )
            )
            for slug, registration in registrations.items()
        }
        self.assertEqual(payment_statuses["valorant"], [PaymentAttempt.Status.PENDING])
        self.assertEqual(payment_statuses["chess"], [])
        self.assertEqual(
            payment_statuses["counter-strike-2"],
            [PaymentAttempt.Status.VERIFIED],
        )
        self.assertEqual(
            payment_statuses["rocket-league"],
            [PaymentAttempt.Status.REJECTED, PaymentAttempt.Status.PENDING],
        )
        rocket_payments = list(
            registrations["rocket-league"].payment_attempts.order_by("pk")
        )
        rejection_event = registrations["rocket-league"].status_events.last()
        self.assertLess(
            rocket_payments[0].reviewed_at,
            rocket_payments[1].created_at,
        )
        self.assertLess(rocket_payments[1].created_at, rejection_event.created_at)
        self.assertTrue(
            all(
                attempt.proof_file.name
                for attempt in PaymentAttempt.objects.filter(
                    registration__submitted_by=player
                )
            )
        )

        event_statuses = {
            slug: list(registration.status_events.values_list("to_status", flat=True))
            for slug, registration in registrations.items()
        }
        self.assertEqual(event_statuses["valorant"], [Registration.Status.SUBMITTED])
        self.assertEqual(
            event_statuses["chess"],
            [
                Registration.Status.SUBMITTED,
                Registration.Status.UNDER_REVIEW,
                Registration.Status.APPROVED,
            ],
        )
        self.assertEqual(
            event_statuses["counter-strike-2"],
            [Registration.Status.SUBMITTED, Registration.Status.UNDER_REVIEW],
        )
        self.assertEqual(
            event_statuses["rocket-league"],
            [
                Registration.Status.SUBMITTED,
                Registration.Status.UNDER_REVIEW,
                Registration.Status.REJECTED,
            ],
        )
        self.assertEqual(
            registrations["rocket-league"].status_events.last().note,
            "Eligibility documents were incomplete.",
        )
        self.assertLess(
            registrations["rocket-league"].submitted_at,
            registrations["rocket-league"].tournament_game.tournament.starts_at,
        )
        self.assertEqual(
            list(
                registrations["rocket-league"].status_events.values_list(
                    "created_at", flat=True
                )
            ),
            sorted(
                registrations["rocket-league"].status_events.values_list(
                    "created_at", flat=True
                )
            ),
        )

    def test_rerun_restores_seed_owned_data_and_preserves_unrelated_records(self):
        self.run_seed()
        user_model = get_user_model()
        player = user_model.objects.get(email="player@email.com")
        organizers = Group.objects.get(name="Organizers")
        changed_institution = Institution.objects.create(label="Changed")
        player.first_name = "Changed"
        player.last_name = "Changed"
        player.institution = changed_institution
        player.student_id = "stale-student-id"
        player.is_staff = True
        player.is_superuser = True
        player.set_unusable_password()
        player.save()
        player.groups.add(organizers)

        current = Tournament.objects.get(slug="dev-usec-current")
        current.name = "Changed"
        current.save(update_fields=("name",))
        Registration.objects.filter(
            submitted_by=player,
            tournament_game__game__slug="valorant",
        ).update(team_name="Changed")
        TournamentGame.objects.filter(
            tournament__slug="dev-usec-current",
            game__slug="valorant",
        ).update(fee_amount=Decimal("1.00"))
        PaymentAttempt.objects.filter(
            registration__submitted_by=player,
            registration__tournament_game__game__slug="valorant",
        ).update(
            status=PaymentAttempt.Status.VERIFIED,
            reference="Changed",
        )

        outsider = user_model.objects.create_user(
            email="outsider@example.com",
            password="strong-password",
            first_name="Outsider",
            last_name="User",
        )
        outsider_game = Game.objects.create(
            name="Unrelated Game", slug="unrelated-game"
        )
        outsider_tournament = Tournament.objects.create(
            name="Unrelated Tournament",
            slug="unrelated-tournament",
            is_published=True,
        )
        outsider_tournament_game = TournamentGame.objects.create(
            tournament=outsider_tournament,
            game=outsider_game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            registration_capacity=None,
            fee_amount=Decimal("0.00"),
            fee_currency="VND",
        )
        outsider_registration = Registration.objects.create(
            tournament_game=outsider_tournament_game,
            submitted_by=outsider,
            team_name="",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=Decimal("0.00"),
            fee_currency_snapshot="VND",
        )

        self.run_seed()

        player.refresh_from_db()
        self.assertTrue(player.check_password("player@123"))
        self.assertEqual(player.first_name, "Development")
        self.assertEqual(player.last_name, "Player")
        self.assertEqual(
            player.institution.label,
            "TRƯỜNG ĐẠI HỌC KHOA HỌC TỰ NHIÊN (ĐẠI HỌC QUỐC GIA TP. HỒ CHÍ MINH)",
        )
        self.assertEqual(player.institution.short_name, "HCMUS")
        self.assertEqual(player.institution.english_name, "University of Science - VNU")
        self.assertEqual(player.institution.source, Institution.Source.CATALOGUE)
        self.assertFalse(hasattr(player, "gamer_tag"))
        self.assertFalse(player.is_staff)
        self.assertFalse(player.is_superuser)
        self.assertFalse(player.groups.exists())
        self.assertEqual(player.student_id, "")
        player.full_clean()
        self.assertEqual(
            Tournament.objects.get(slug="dev-usec-current").name,
            "USEC Development Open",
        )

        seeded_registrations = Registration.objects.filter(
            submitted_by=player,
            tournament_game__tournament__slug__in=(
                "dev-usec-current",
                "dev-usec-archive",
                "dev-usec-draft",
            ),
        )
        self.assertEqual(seeded_registrations.count(), 4)
        self.assertEqual(
            PaymentAttempt.objects.filter(
                registration__in=seeded_registrations
            ).count(),
            4,
        )
        self.assertEqual(
            RegistrationStatusEvent.objects.filter(
                registration__in=seeded_registrations
            ).count(),
            9,
        )
        self.assertEqual(
            seeded_registrations.get(tournament_game__game__slug="valorant").team_name,
            "Blue Phoenix",
        )
        self.assertEqual(
            TournamentGame.objects.get(
                tournament__slug="dev-usec-current",
                game__slug="valorant",
            ).fee_amount,
            Decimal("50000.00"),
        )
        restored_payment = PaymentAttempt.objects.get(
            registration__submitted_by=player,
            registration__tournament_game__game__slug="valorant",
        )
        self.assertEqual(restored_payment.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(restored_payment.reference, "DEV-VAL-PENDING")
        self.assertTrue(
            Registration.objects.filter(pk=outsider_registration.pk).exists()
        )
        self.assertTrue(Tournament.objects.filter(pk=outsider_tournament.pk).exists())

    def test_seed_failure_rolls_back_bootstrap_accounts_and_catalog(self):
        with patch(
            "registrations.dev_seed._rebuild_registrations",
            side_effect=ValidationError("forced failure"),
        ):
            with self.assertRaises(CommandError):
                self.run_seed()

        self.assertFalse(
            get_user_model()
            .objects.filter(
                email__in=(
                    "player@email.com",
                    "organizer@email.com",
                    "admin@email.com",
                )
            )
            .exists()
        )
        self.assertFalse(Group.objects.filter(name="Organizers").exists())
        self.assertFalse(
            Game.objects.filter(
                slug__in=(
                    "valorant",
                    "chess",
                    "counter-strike-2",
                    "league-of-legends",
                    "rocket-league",
                    "ea-sports-fc",
                    "arena-of-valor",
                )
            ).exists()
        )
        self.assertFalse(
            Tournament.objects.filter(
                slug__in=(
                    "dev-usec-current",
                    "dev-usec-archive",
                    "dev-usec-draft",
                    "dev-sponsor-open",
                    "dev-sponsor-arena",
                    "dev-sponsor-expired",
                    "dev-fpt-shop-uni-tour-2026",
                )
            ).exists()
        )
        self.assertFalse(Institution.objects.exists())

    def test_round_robin_fixtures_preserve_schedules_results_and_tie_history_on_rerun(
        self,
    ):
        from collections import Counter
        from competitions.models import TieResolution

        self.run_seed()
        stages = Stage.objects.filter(
            competition__tournament_game__tournament__slug="dev-usec-round-robin"
        ).order_by("pk")
        self.assertEqual(stages.count(), 2)
        snapshots = []
        for stage in stages:
            draw = stage.draws.get(state="PUBLISHED")
            groups = list(draw.groups.all())
            self.assertEqual(
                [g.entries.count() for g in groups],
                [3, 5] if stage.round_robin_meetings == 1 else [4, 4],
            )
            matches = list(
                Match.objects.filter(
                    round__draw=draw, round__section="NORMAL"
                ).prefetch_related("slots")
            )
            pairs = Counter(
                tuple(sorted(s.entry_id for s in m.slots.all())) for m in matches
            )
            self.assertEqual(set(pairs.values()), {stage.round_robin_meetings})
            self.assertEqual(
                len(matches), 13 if stage.round_robin_meetings == 1 else 24
            )
            snapshots.append(
                (
                    draw.pk,
                    list(
                        Match.objects.filter(round__draw=draw).values_list(
                            "pk", "status", "side_one_score", "side_two_score"
                        )
                    ),
                )
            )
        self.assertTrue(
            TieResolution.objects.filter(
                group__draw__stage__in=stages, method="MANUAL"
            ).exists()
        )
        self.assertTrue(
            TieResolution.objects.filter(
                group__draw__stage__in=stages, state="SUPERSEDED"
            ).exists()
        )
        self.run_seed()
        for draw_id, matches in snapshots:
            self.assertEqual(
                list(
                    Match.objects.filter(round__draw_id=draw_id).values_list(
                        "pk", "status", "side_one_score", "side_two_score"
                    )
                ),
                matches,
            )

    def test_multi_stage_seed_preserves_published_draws_and_unequal_group_rules(self):
        self.run_seed()
        competitions = list(
            Competition.objects.filter(
                tournament_game__tournament__slug="dev-usec-multi-stage"
            ).order_by("pk")
        )
        self.assertEqual(len(competitions), 3)
        ids = []
        for competition in competitions:
            self.assertEqual(competition.stages.count(), 2)
            source, destination = list(competition.stages.all())
            sizes = list(source.group_plans.values_list("size", flat=True))
            self.assertIn(sizes, ([3, 3, 2], [3, 2, 2], [2, 5, 3]))
            draw = destination.draws.get(state="PUBLISHED")
            self.assertEqual(draw.entries.count(), 7 if sizes == [2, 5, 3] else 6)
            self.assertEqual(draw.entries.filter(source_entry__isnull=True).count(), 0)
            ids.extend(
                Match.objects.filter(round__draw=draw).values_list("pk", flat=True)
            )
        before = list(
            Match.objects.filter(pk__in=ids).values_list(
                "pk", "code", "side_one_score", "side_two_score"
            )
        )
        self.run_seed()
        self.assertEqual(
            list(
                Match.objects.filter(pk__in=ids).values_list(
                    "pk", "code", "side_one_score", "side_two_score"
                )
            ),
            before,
        )

    def test_swiss_seed_preserves_complete_chains_rounds_limits_and_scores(self):
        self.run_seed()
        competitions = list(
            Competition.objects.filter(
                tournament_game__tournament__slug="dev-usec-swiss"
            ).order_by("tournament_game__game__slug")
        )
        self.assertEqual(len(competitions), 2)
        snapshots = []
        for competition in competitions:
            stages = list(competition.stages.all())
            self.assertEqual(stages[-1].format, "SINGLE_ELIMINATION")
            self.assertEqual(stages[0].status, "COMPLETE")
            source = stages[0].draws.get(state="PUBLISHED")
            if stages[0].format == "SWISS_FIXED":
                self.assertEqual(source.entries.count(), 9)
                self.assertEqual(source.swiss_round_limit, 4)
                self.assertEqual(stages[0].series_mode, "FIXED_GAMES")
                self.assertEqual(stages[0].default_series_length, 2)
                self.assertEqual(source.rounds.filter(state="PUBLISHED").count(), 4)
                self.assertEqual(stages[0].advancement_count, 4)
                self.assertEqual(
                    Match.objects.filter(round__draw=source, outcome="BYE").count(), 4
                )
            else:
                self.assertEqual(source.entries.count(), 16)
                self.assertEqual(
                    (stages[0].swiss_win_target, stages[0].swiss_loss_limit), (3, 3)
                )
                self.assertEqual(len(stages), 3)
                self.assertEqual(stages[1].format, "SWISS_FIXED")
                self.assertIsNone(stages[1].swiss_round_count)
                self.assertEqual(stages[1].status, "COMPLETE")
                self.assertEqual(stages[1].advancement_count, 4)
            for stage in stages[1:]:
                draw = stage.draws.get(state="PUBLISHED")
                self.assertFalse(
                    draw.entries.filter(source_entry__isnull=True).exists()
                )
            self.assertEqual(stages[-1].draws.get(state="PUBLISHED").entries.count(), 4)
            snapshots.append(
                (
                    competition.pk,
                    list(
                        StageDraw.objects.filter(
                            stage__competition=competition
                        ).values_list("pk", "swiss_round_limit")
                    ),
                    list(
                        Round.objects.filter(
                            draw__stage__competition=competition
                        ).values_list("pk", "state", "version")
                    ),
                    list(
                        Match.objects.filter(
                            round__draw__stage__competition=competition
                        ).values_list(
                            "pk", "status", "side_one_score", "side_two_score"
                        )
                    ),
                )
            )
        self.run_seed()
        for competition_id, draws, rounds, matches in snapshots:
            self.assertEqual(
                list(
                    StageDraw.objects.filter(
                        stage__competition_id=competition_id
                    ).values_list("pk", "swiss_round_limit")
                ),
                draws,
            )
            self.assertEqual(
                list(
                    Round.objects.filter(
                        draw__stage__competition_id=competition_id
                    ).values_list("pk", "state", "version")
                ),
                rounds,
            )
            self.assertEqual(
                list(
                    Match.objects.filter(
                        round__draw__stage__competition_id=competition_id
                    ).values_list("pk", "status", "side_one_score", "side_two_score")
                ),
                matches,
            )
