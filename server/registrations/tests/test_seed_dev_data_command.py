from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from registrations.models import PaymentAttempt, Registration, RegistrationStatusEvent
from tournaments.models import Game, Tournament, TournamentGame


@override_settings(DEBUG=True)
class SeedDevDataCommandTests(TestCase):
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
        self.assertEqual(player.gamer_tag, "Rookie")
        self.assertEqual(player.school, "HCMUS")
        self.assertTrue(player.is_active)
        self.assertFalse(player.is_staff)
        self.assertFalse(player.is_superuser)
        self.assertFalse(player.groups.exists())

        self.assertTrue(organizer.check_password("organizer@123"))
        self.assertTrue(organizer.is_active)
        self.assertTrue(organizer.is_staff)
        self.assertFalse(organizer.is_superuser)
        self.assertSetEqual(
            set(organizer.groups.values_list("name", flat=True)),
            {"Organizers"},
        )
        self.assertTrue(organizer.has_perm("registrations.change_registration"))
        self.assertTrue(organizer.has_perm("registrations.change_paymentattempt"))
        self.assertFalse(organizer.has_perm("registrations.delete_registration"))

        self.assertTrue(admin.check_password("admin@123"))
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertFalse(admin.groups.exists())

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
            {"dev-usec-current", "dev-usec-archive"},
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
        self.assertFalse(
            any(
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
        player.gamer_tag = "Changed"
        player.school = "Changed"
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
            team_size_min=1,
            team_size_max=1,
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
        self.assertEqual(player.gamer_tag, "Rookie")
        self.assertEqual(player.school, "HCMUS")
        self.assertFalse(player.is_staff)
        self.assertFalse(player.is_superuser)
        self.assertFalse(player.groups.exists())
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
            "registrations.dev_seed._seed_catalog",
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
            Tournament.objects.filter(slug__startswith="dev-usec-").exists()
        )
