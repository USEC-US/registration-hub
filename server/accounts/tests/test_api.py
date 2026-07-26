from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test.utils import ignore_warnings
from jwt.warnings import InsecureKeyLengthWarning
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.tests.factories import create_account


@override_settings(ROOT_URLCONF="config.urls")
class AccountApiTests(APITestCase):
    def test_register_creates_email_login_user(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "player@example.com",
                "password": "strong-password-123",
                "first_name": "Minh",
                "last_name": "Nguyen",
                "school": "HCMUS",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(email="player@example.com")
        self.assertEqual(user.first_name, "Minh")
        self.assertEqual(user.last_name, "Nguyen")
        self.assertEqual(user.school, "HCMUS")
        self.assertNotIn("gamer_tag", response.data)
        self.assertNotIn("password", response.data)

    def test_register_requires_first_and_last_name(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "player@example.com", "password": "strong-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", response.data)
        self.assertIn("last_name", response.data)

    def test_register_rejects_duplicate_email(self):
        create_account(
            email="player@example.com",
            password="strong-password-123",
        )

        response = self.client.post(
            "/api/auth/register/",
            {"email": "player@example.com", "password": "strong-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    @ignore_warnings(category=InsecureKeyLengthWarning)
    def test_token_endpoint_accepts_email_password(self):
        create_account(
            email="player@example.com",
            password="strong-password-123",
        )

        response = self.client.post(
            "/api/auth/token/",
            {"email": "player@example.com", "password": "strong-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_current_user_requires_authentication(self):
        response = self.client.get("/api/account/me/")

        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_current_user_read_and_patch(self):
        user = create_account(
            email="player@example.com",
            password="strong-password-123",
            first_name="Old",
            last_name="Name",
            school="Old School",
        )
        self.client.force_authenticate(user=user)

        get_response = self.client.get("/api/account/me/")
        patch_response = self.client.patch(
            "/api/account/me/",
            {
                "first_name": "New",
                "last_name": "Name",
                "school": "HCMUS",
                "email": "other@example.com",
            },
            format="json",
        )

        user.refresh_from_db()
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["email"], "player@example.com")
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.email, "player@example.com")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Name")
        self.assertEqual(user.school, "HCMUS")
