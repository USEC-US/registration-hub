from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.tests.factories import create_account

@override_settings(ROOT_URLCONF="config.urls")
class SchemaDocsAccessTests(APITestCase):
    @override_settings(DEBUG=True)
    def test_schema_and_docs_are_public_in_debug(self):
        schema_response = self.client.get("/api/schema/")
        docs_response = self.client.get("/api/docs/")

        self.assertEqual(schema_response.status_code, status.HTTP_200_OK)
        self.assertEqual(docs_response.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=True)
    def test_schema_uses_stable_types_and_enum_names(self):
        response = self.client.get(
            "/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        schema = response.json()
        detail_parameters = schema["paths"]["/api/registrations/{id}/"]["get"]["parameters"]
        identifier_parameter = next(
            parameter for parameter in detail_parameters if parameter["name"] == "id"
        )

        self.assertEqual(identifier_parameter["schema"]["type"], "integer")
        self.assertIn("RegistrationStatus", schema["components"]["schemas"])
        self.assertIn("PaymentAttemptStatus", schema["components"]["schemas"])

    @override_settings(DEBUG=False)
    def test_schema_is_staff_only_outside_debug(self):
        anonymous_response = self.client.get("/api/schema/")
        staff_user = create_account(
            email="staff@example.com",
            password="strong-password",
            first_name="Organizer",
            last_name="Staff",
            is_staff=True,
        )

        self.client.force_authenticate(user=staff_user)
        staff_response = self.client.get("/api/schema/")

        self.assertEqual(anonymous_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(staff_response.status_code, status.HTTP_200_OK)
