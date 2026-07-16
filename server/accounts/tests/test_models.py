from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase


class UserModelTests(TestCase):
    def test_email_is_the_login_identifier(self):
        user = get_user_model().objects.create_user(
            email="captain@example.com",
            password="strong-password",
            gamer_tag="captain",
            school="HCMUS",
        )

        self.assertEqual(get_user_model().USERNAME_FIELD, "email")
        self.assertEqual(user.email, "captain@example.com")
        self.assertTrue(user.check_password("strong-password"))

    def test_email_is_unique(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            email="same@example.com", password="strong-password"
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            user_model.objects.create_user(
                email="same@example.com", password="another-password"
            )
