from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tournaments.models import Tournament


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
                "counter-strike-2": "open",
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
        self.assertFalse(
            Tournament.objects.get(slug="dev-usec-draft").is_published
        )
