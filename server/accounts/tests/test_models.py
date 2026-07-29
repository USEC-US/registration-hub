from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import Institution
from accounts.tests.factories import create_account


class UserModelTests(TestCase):
    def test_email_is_the_login_identifier(self):
        user = create_account(
            email="captain@example.com",
            password="strong-password",
            first_name="Captain",
            last_name="Player",
        )

        self.assertEqual(get_user_model().USERNAME_FIELD, "email")
        self.assertEqual(user.email, "captain@example.com")
        self.assertTrue(user.check_password("strong-password"))

    def test_email_is_unique(self):
        create_account(
            email="same@example.com",
            password="strong-password",
            first_name="Same",
            last_name="User",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            create_account(
                email="same@example.com",
                password="another-password",
                first_name="Same",
                last_name="User",
            )

    def test_create_user_requires_first_name(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user(
                email="player@example.com",
                password="strong-password",
                last_name="User",
            )

    def test_create_user_requires_last_name(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user(
                email="player@example.com",
                password="strong-password",
                first_name="Test",
            )

    def test_create_user_rejects_student_id_for_non_staff_user(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user(
                email="player@example.com",
                password="strong-password",
                first_name="Test",
                last_name="User",
                student_id="22120001",
            )

    def test_create_user_requires_student_id_for_staff_user(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user(
                email="staff@example.com",
                password="strong-password",
                first_name="Staff",
                last_name="User",
                is_staff=True,
            )

    def test_create_user_accepts_student_id_for_staff_user(self):
        user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="strong-password",
            first_name="Staff",
            last_name="User",
            is_staff=True,
            student_id="22120001",
        )

        self.assertEqual(user.student_id, "22120001")


class InstitutionModelTests(TestCase):
    def test_renaming_updates_normalized_label_with_update_fields(self):
        institution = Institution.objects.create(
            label="Original Academy",
            source=Institution.Source.CUSTOM,
        )

        institution.label = "  Renamed Academy  "
        institution.save(update_fields=("label",))
        institution.refresh_from_db()

        self.assertEqual(institution.normalized_label, "renamed academy")
