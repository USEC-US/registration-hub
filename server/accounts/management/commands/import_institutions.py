import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Institution
from accounts.services.institutions import normalize_institution_label


class Command(BaseCommand):
    help = "Import the institution catalogue from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=Path,
            default=settings.BASE_DIR / "university.json",
            help="Path to the institution catalogue JSON file.",
        )

    def handle(self, *args, **options):
        path = options["path"]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CommandError(f"Unable to load institution catalogue: {error}") from error

        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise CommandError("Institution catalogue payload must contain a data list.")

        created_count = 0
        updated_count = 0
        for record in records:
            if not isinstance(record, dict):
                raise CommandError("Institution catalogue data entries must be objects.")

            try:
                value = str(record["value"])
                label = record["label"].strip()
            except (KeyError, AttributeError) as error:
                raise CommandError(
                    "Institution catalogue entries require string value and label fields."
                ) from error

            _, created = Institution.objects.update_or_create(
                source=Institution.Source.CATALOGUE,
                value=value,
                defaults={
                    "label": label,
                    "normalized_label": normalize_institution_label(label),
                    "code": record.get("code", "").strip(),
                    "short_name": record.get("shortName", "").strip(),
                    "english_name": record.get("eng", "").strip(),
                    "type": record.get("type", "").strip(),
                    "location": record.get("location", "").strip(),
                    "review_status": Institution.ReviewStatus.VERIFIED,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported institutions: {created_count} created, {updated_count} updated."
            )
        )
