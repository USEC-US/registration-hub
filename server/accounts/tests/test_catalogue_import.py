import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import Institution


class CatalogueImportSafetyTests(TestCase):
    def run_import(self, records, **options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.json"
            path.write_text(json.dumps({"data": records}), encoding="utf-8")
            output = StringIO()
            call_command("import_institutions", path=path, stdout=output, **options)
            return output.getvalue()

    def test_invalid_late_record_leaves_database_unchanged(self):
        with self.assertRaises(CommandError):
            self.run_import(
                [{"value": "1", "label": "Valid"}, {"value": "2", "label": " "}]
            )
        self.assertFalse(Institution.objects.exists())

    def test_duplicate_values_and_wrong_field_types_are_rejected(self):
        for records in (
            [{"value": "1", "label": "One"}, {"value": "1", "label": "Two"}],
            [{"value": None, "label": "One"}],
            [{"value": "1", "label": "One", "code": 123}],
            [{"value": "1", "label": "One", "aliases": "not a list"}],
        ):
            with self.subTest(records=records), self.assertRaises(CommandError):
                self.run_import(records)
        self.assertFalse(Institution.objects.exists())

    def test_dry_run_reports_changes_without_writing(self):
        output = self.run_import([{"value": "1", "label": "One"}], dry_run=True)
        self.assertIn("1 created", output)
        self.assertFalse(Institution.objects.exists())

    def test_import_preserves_identity_review_decisions_and_custom_entries(self):
        existing = Institution.objects.create(
            value="222", label="Old name", source="CATALOGUE", review_status="REJECTED"
        )
        custom = Institution.objects.create(
            label="Community school", review_status="VERIFIED"
        )
        records = [
            {
                "value": "222",
                "label": "New name",
                "aliases": ["Old name"],
                "domains": ["hcmus.edu.vn"],
                "provenance": [{"source": "moet", "id": "upstream-id"}],
            }
        ]
        self.run_import(records)
        existing.refresh_from_db()
        custom.refresh_from_db()
        self.assertEqual(existing.label, "New name")
        self.assertEqual(existing.review_status, "REJECTED")
        self.assertEqual(existing.aliases, ["Old name"])
        self.assertEqual(existing.domains, ["hcmus.edu.vn"])
        self.assertEqual(existing.provenance[0]["id"], "upstream-id")
        self.assertEqual(custom.source, "CUSTOM")
        self.assertEqual(custom.review_status, "VERIFIED")
        self.assertIn("1 unchanged", self.run_import(records))

    def test_database_failure_rolls_back_the_whole_import(self):
        save = Institution.save

        def failing_save(instance, *args, **kwargs):
            if instance.value == "2":
                raise RuntimeError("Storage failure")
            return save(instance, *args, **kwargs)

        with (
            patch.object(Institution, "save", failing_save),
            self.assertRaises(RuntimeError),
        ):
            self.run_import(
                [{"value": "1", "label": "One"}, {"value": "2", "label": "Two"}]
            )
        self.assertFalse(Institution.objects.exists())
