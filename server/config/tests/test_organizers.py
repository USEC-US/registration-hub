from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from accounts.tests.factories import create_account
from config.organizers import is_organizer_staff, require_organizer


class OrganizerAuthorizationTests(TestCase):
    def setUp(self):
        self.permission = Permission.objects.get(
            content_type__app_label="tournaments", codename="view_tournament"
        )

    def test_requires_active_staff_membership_and_permission(self):
        organizer = create_account(
            email="organizer@example.com",
            password="strong-password",
            first_name="Organizer",
            last_name="Staff",
            is_staff=True,
        )
        organizer.groups.add(Group.objects.create(name="Organizers"))

        self.assertTrue(is_organizer_staff(organizer))
        with self.assertRaises(PermissionDenied):
            require_organizer(organizer, "tournaments.view_tournament")

        organizer.user_permissions.add(self.permission)
        organizer = type(organizer).objects.get(pk=organizer.pk)
        require_organizer(organizer, "tournaments.view_tournament")

        organizer.is_active = False
        organizer.save(update_fields=("is_active",))
        self.assertFalse(is_organizer_staff(organizer))

    def test_superuser_is_allowed_without_group_membership(self):
        superuser = create_account(
            email="admin@example.com",
            password="strong-password",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_superuser=True,
        )

        require_organizer(superuser, "tournaments.view_tournament")
