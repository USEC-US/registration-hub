from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import Institution
from accounts.services.institutions import resolve_institution
from accounts.tests.factories import create_account


@override_settings(ROOT_URLCONF="config.urls", DEBUG=True, TURNSTILE_SECRET_KEY="")
class InstitutionReviewTests(APITestCase):
    def test_profile_can_keep_its_existing_pending_institution(self):
        school = resolve_institution(
            institution_id=None, institution_label="New university"
        )
        user = create_account(institution=school)
        self.client.force_authenticate(user)
        response = self.client.patch(
            "/api/account/me/", {"first_name": "Updated", "institution_id": school.pk}
        )
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Updated")
        self.assertEqual(user.institution_id, school.pk)

    def test_verified_community_entry_can_be_found_and_selected(self):
        school = resolve_institution(
            institution_id=None, institution_label="New Community University"
        )
        self.assertEqual(self.client.get("/api/institutions/?q=Community").data, [])
        school.review_status = "VERIFIED"
        school.save()
        result = self.client.get("/api/institutions/?q=Community")
        self.assertEqual([row["id"] for row in result.data], [school.pk])
        self.assertEqual(
            resolve_institution(institution_id=school.pk, institution_label=None),
            school,
        )
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "student@example.com",
                "password": "A-unique-password-743!",
                "first_name": "Lan",
                "last_name": "Tran",
                "institution_id": school.pk,
            },
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_rejected_or_pending_entries_cannot_be_selected_by_id(self):
        for source in ("CATALOGUE", "CUSTOM"):
            for status in ("REJECTED", "PENDING"):
                school = Institution.objects.create(
                    value=f"{source}-{status}",
                    label=f"School {source} {status}",
                    source=source,
                    review_status=status,
                )
                with self.subTest(source=source, status=status):
                    self.assertEqual(
                        self.client.get("/api/institutions/", {"q": school.label}).data,
                        [],
                    )
                    response = self.client.post(
                        "/api/auth/register/",
                        {
                            "email": "student@example.com",
                            "password": "A-unique-password-743!",
                            "first_name": "Lan",
                            "last_name": "Tran",
                            "institution_id": school.pk,
                        },
                    )
                    self.assertEqual(response.status_code, 400)

    def test_alias_and_domain_search_returns_distinct_schools(self):
        hcm = Institution.objects.create(
            value="222",
            label="Science, VNU-HCM",
            source="CATALOGUE",
            review_status="VERIFIED",
            aliases=["HCMUS", "Đại học Khoa học Tự nhiên TP.HCM"],
            domains=["hcmus.edu.vn"],
        )
        Institution.objects.create(
            value="215",
            label="Science, VNU-HN",
            source="CATALOGUE",
            review_status="VERIFIED",
            aliases=["HUS"],
            domains=["hus.edu.vn"],
        )
        for query in ("HCMUS", "hcmus.edu.vn", "Tự nhiên"):
            result = self.client.get("/api/institutions/", {"q": query})
            self.assertEqual([row["id"] for row in result.data], [hcm.pk])
            self.assertNotIn("provenance", result.data[0])
