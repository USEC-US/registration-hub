from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(ROOT_URLCONF="config.urls")
class SchemaDocsAccessTests(APITestCase):
    @override_settings(DEBUG=True)
    def test_schema_and_docs_are_public_in_debug(self):
        schema_response = self.client.get("/api/schema/")
        docs_response = self.client.get("/api/docs/")

        self.assertEqual(schema_response.status_code, status.HTTP_200_OK)
        self.assertEqual(docs_response.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=False)
    def test_schema_is_staff_only_outside_debug(self):
        anonymous_response = self.client.get("/api/schema/")
        staff_user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="strong-password",
            is_staff=True,
        )

        self.client.force_authenticate(user=staff_user)
        staff_response = self.client.get("/api/schema/")

        self.assertEqual(anonymous_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(staff_response.status_code, status.HTTP_200_OK)
