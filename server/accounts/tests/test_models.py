from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.tests.factories import create_account


class UserModelTests(TestCase):
    def test_email_is_the_login_identifier(self):
        user = create_account(
            email="captain@example.com",
            password="strong-password",
            first_name="Captain",
            last_name="Player",
            school="HCMUS",
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
