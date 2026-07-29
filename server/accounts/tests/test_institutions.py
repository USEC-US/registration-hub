import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import Institution
from accounts.services.institutions import resolve_institution


class InstitutionResolutionTests(TestCase):
    def test_custom_label_is_normalized_and_reused(self):
        first = resolve_institution(institution_id=None, institution_label="  HCMUS  ")
        second = resolve_institution(institution_id=None, institution_label="hcmus")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.source, Institution.Source.CUSTOM)
        self.assertEqual(first.review_status, Institution.ReviewStatus.PENDING)
        self.assertEqual(first.label, "HCMUS")

    def test_catalogue_label_wins_over_a_new_custom_record(self):
        catalogue = Institution.objects.create(
            value="227",
            label="University of Science",
            source=Institution.Source.CATALOGUE,
        )

        resolved = resolve_institution(
            institution_id=None,
            institution_label=" university of science ",
        )

        self.assertEqual(resolved.pk, catalogue.pk)


class InstitutionImportCommandTests(TestCase):
    def write_payload(self, payload):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "institutions.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_import_is_idempotent_for_catalogue_records(self):
        path = self.write_payload(
            {
                "data": [
                    {
                        "value": "227",
                        "label": "University of Science",
                        "code": "HCMUS",
                        "shortName": "VNUHCM-US",
                        "eng": "University of Science",
                        "type": "National university",
                        "location": "Ho Chi Minh City",
                    }
                ]
            }
        )

        call_command("import_institutions", path=path)
        call_command("import_institutions", path=path)

        institution = Institution.objects.get(value="227")
        self.assertEqual(Institution.objects.filter(value="227").count(), 1)
        self.assertEqual(institution.label, "University of Science")
        self.assertEqual(institution.review_status, Institution.ReviewStatus.VERIFIED)
        self.assertEqual(institution.short_name, "VNUHCM-US")

    def test_import_does_not_change_custom_pending_records(self):
        custom = Institution.objects.create(
            label="University of Science",
            normalized_label="university of science",
            source=Institution.Source.CUSTOM,
            review_status=Institution.ReviewStatus.PENDING,
        )
        path = self.write_payload(
            {
                "data": [
                    {
                        "value": "227",
                        "label": "University of Science",
                        "code": "HCMUS",
                    }
                ]
            }
        )

        call_command("import_institutions", path=path)

        custom.refresh_from_db()
        self.assertEqual(custom.source, Institution.Source.CUSTOM)
        self.assertEqual(custom.review_status, Institution.ReviewStatus.PENDING)
        self.assertEqual(custom.value, "")
        self.assertEqual(custom.code, "")

    def test_import_rejects_payload_without_a_data_list(self):
        path = self.write_payload({"data": {}})

        with self.assertRaises(CommandError):
            call_command("import_institutions", path=path)
