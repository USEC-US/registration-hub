from django.contrib.auth import get_user_model
from unittest.mock import patch

from django.test import override_settings
from django.test.utils import ignore_warnings
from jwt.warnings import InsecureKeyLengthWarning
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Institution
from accounts.tests.factories import create_account


@override_settings(ROOT_URLCONF="config.urls", DEBUG=True, TURNSTILE_SECRET_KEY="")
class AccountApiTests(APITestCase):
    def create_catalogue_institution(self, **overrides):
        fields = {
            "value": "227",
            "label": "University of Science",
            "normalized_label": "university of science",
            "code": "HCMUS",
            "short_name": "VNUHCM-US",
            "english_name": "University of Science",
            "type": "National university",
            "location": "Ho Chi Minh City",
            "source": Institution.Source.CATALOGUE,
            "review_status": Institution.ReviewStatus.VERIFIED,
        }
        fields.update(overrides)
        return Institution.objects.create(**fields)

    def registration_payload(self, **overrides):
        payload = {
            "email": "player@example.com",
            "password": "strong-password-123",
            "first_name": "Minh",
            "last_name": "Nguyen",
        }
        payload.update(overrides)
        return payload

    def test_institution_search_returns_catalogue_matches(self):
        catalogue = self.create_catalogue_institution()
        Institution.objects.create(
            label="Science Club",
            normalized_label="science club",
            source=Institution.Source.CUSTOM,
        )

        response = self.client.get("/api/institutions/?q=science")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["id"], catalogue.pk)
        self.assertEqual(response.data[0]["label"], "University of Science")
        self.assertEqual(response.data[0]["shortName"], "VNUHCM-US")
        self.assertEqual(response.data[0]["eng"], "University of Science")

    def test_register_uses_catalogue_institution(self):
        institution = self.create_catalogue_institution()

        response = self.client.post(
            "/api/auth/register/",
            self.registration_payload(
                institution_id=institution.pk,
                turnstile_token="debug-token",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(email="player@example.com")
        self.assertEqual(user.first_name, "Minh")
        self.assertEqual(user.last_name, "Nguyen")
        self.assertEqual(user.institution, institution)
        self.assertEqual(response.data["institution"]["id"], institution.pk)
        self.assertNotIn("password", response.data)

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_register_requires_turnstile_outside_debug(self):
        response = self.client.post(
            "/api/auth/register/",
            self.registration_payload(institution_label="University of Science"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("turnstile_token", response.data)

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="secret")
    def test_rejected_registration_does_not_create_a_custom_institution(self):
        user_count = get_user_model().objects.count()
        institution_count = Institution.objects.count()
        with patch("config.turnstile.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"success": false, "error-codes": ["invalid-input-response"]}'
            )
            response = self.client.post(
                "/api/auth/register/",
                self.registration_payload(
                    institution_label="Rejected Academy",
                    turnstile_token="invalid-token",
                ),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(get_user_model().objects.count(), user_count)
        self.assertEqual(Institution.objects.count(), institution_count)

    @override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
    def test_register_allows_debug_bypass_when_secret_missing(self):
        response = self.client.post(
            "/api/auth/register/",
            self.registration_payload(institution_label="University of Science"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_register_creates_pending_custom_institution_without_exposing_private_fields(
        self,
    ):
        response = self.client.post(
            "/api/auth/register/",
            self.registration_payload(institution_label="New Academy"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["institution"]["label"], "New Academy")
        self.assertNotIn("student_id", response.data)
        self.assertNotIn("source", response.data["institution"])
        self.assertNotIn("review_status", response.data["institution"])
        self.assertNotIn("normalized_label", response.data["institution"])

    def test_register_rejects_invalid_institution_choices(self):
        catalogue = self.create_catalogue_institution()
        invalid_choices = (
            {},
            {"institution_id": catalogue.pk, "institution_label": "New Academy"},
            {"institution_id": 999999},
            {"institution_label": "   "},
        )

        for choice in invalid_choices:
            with self.subTest(choice=choice):
                response = self.client.post(
                    "/api/auth/register/",
                    self.registration_payload(email=f"{len(choice)}@example.com", **choice),
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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
            self.registration_payload(),
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

    @ignore_warnings(category=InsecureKeyLengthWarning)
    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_token_endpoint_requires_turnstile_outside_debug(self):
        create_account(
            email="player@example.com",
            password="strong-password-123",
        )

        response = self.client.post(
            "/api/auth/token/",
            {"email": "player@example.com", "password": "strong-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("turnstile_token", response.data)

    def test_current_user_requires_authentication(self):
        response = self.client.get("/api/account/me/")

        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_current_user_read_and_patch_institution_without_exposing_private_fields(self):
        catalogue = self.create_catalogue_institution()
        user = create_account(
            email="player@example.com",
            password="strong-password-123",
            first_name="Old",
            last_name="Name",
            institution=catalogue,
            is_staff=True,
            student_id="22120001",
        )
        self.client.force_authenticate(user=user)

        get_response = self.client.get("/api/account/me/")
        patch_response = self.client.patch(
            "/api/account/me/",
            {
                "first_name": "New",
                "last_name": "Name",
                "institution_id": catalogue.pk,
                "email": "other@example.com",
            },
            format="json",
        )

        user.refresh_from_db()
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["email"], "player@example.com")
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.email, "player@example.com")
        self.assertEqual(user.student_id, "22120001")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Name")
        self.assertEqual(user.institution, catalogue)
        self.assertNotIn("student_id", get_response.data)
        self.assertNotIn("source", get_response.data["institution"])
        self.assertNotIn("review_status", get_response.data["institution"])
        self.assertNotIn("normalized_label", get_response.data["institution"])

        custom_patch_response = self.client.patch(
            "/api/account/me/",
            {"institution_label": "New Academy"},
            format="json",
        )
        user.refresh_from_db()

        self.assertEqual(custom_patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.email, "player@example.com")
        self.assertEqual(user.student_id, "22120001")
        self.assertEqual(user.institution.label, "New Academy")
