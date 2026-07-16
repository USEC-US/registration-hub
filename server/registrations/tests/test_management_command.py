from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase


class BootstrapOrganizersCommandTests(TestCase):
    expected_permissions = {
        "tournaments.add_game",
        "tournaments.change_game",
        "tournaments.view_game",
        "tournaments.add_tournament",
        "tournaments.change_tournament",
        "tournaments.view_tournament",
        "tournaments.add_tournamentgame",
        "tournaments.change_tournamentgame",
        "tournaments.view_tournamentgame",
        "registrations.view_registration",
        "registrations.change_registration",
        "registrations.view_registrationmember",
        "registrations.view_paymentattempt",
        "registrations.change_paymentattempt",
        "registrations.view_registrationstatusevent",
    }

    def test_command_sets_only_the_v1_organizer_permissions(self):
        call_command("bootstrap_organizers")

        group = Group.objects.get(name="Organizers")
        actual_permissions = {
            f"{permission.content_type.app_label}.{permission.codename}"
            for permission in group.permissions.select_related("content_type")
        }

        self.assertSetEqual(actual_permissions, self.expected_permissions)
        self.assertNotIn("registrations.delete_registration", actual_permissions)
        self.assertNotIn("registrations.add_registration", actual_permissions)

    def test_command_is_idempotent(self):
        call_command("bootstrap_organizers")
        call_command("bootstrap_organizers")

        self.assertEqual(Group.objects.filter(name="Organizers").count(), 1)
