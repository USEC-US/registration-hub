import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Institution
from accounts.services.institutions import normalize_institution_label


def validate_records(payload):
    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise CommandError("Institution catalogue payload must contain a data list.")
    values = set()
    validated = []
    fields = {
        "label": "label",
        "code": "code",
        "shortName": "short_name",
        "eng": "english_name",
        "type": "type",
        "location": "location",
    }
    for index, record in enumerate(records, 1):
        try:
            if not isinstance(record, dict):
                raise ValueError("entries must be objects")
            value = record.get("value")
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ValueError("value must be a non-empty string or integer")
            value = str(value).strip()
            if not value or value in values:
                raise ValueError("value must be non-empty and unique within the file")
            values.add(value)
            defaults = {}
            for key, field in fields.items():
                text = record.get(key, "")
                if not isinstance(text, str):
                    raise ValueError(f"{key} must be a string")
                defaults[field] = " ".join(text.split())
            if not defaults["label"]:
                raise ValueError("label must not be blank")
            for field in ("aliases", "domains", "provenance"):
                items = record.get(field, [])
                if not isinstance(items, list):
                    raise ValueError(f"{field} must be a list")
                if field == "provenance":
                    if any(not isinstance(item, dict) for item in items):
                        raise ValueError("provenance entries must be objects")
                else:
                    if any(
                        not isinstance(item, str) or not item.strip() for item in items
                    ):
                        raise ValueError(f"{field} entries must be non-empty strings")
                    items = list(
                        dict.fromkeys(" ".join(item.split()) for item in items)
                    )
                defaults[field] = items
            review_status = record.get(
                "review_status", Institution.ReviewStatus.VERIFIED
            )
            if review_status not in Institution.ReviewStatus.values:
                raise ValueError("invalid review_status")
            defaults["normalized_label"] = normalize_institution_label(
                defaults["label"]
            )
            candidate = Institution(
                value=value,
                source=Institution.Source.CATALOGUE,
                review_status=review_status,
                **defaults,
            )
            candidate.clean_fields()
            validated.append((value, defaults, review_status))
        except (ValueError, ValidationError) as error:
            raise CommandError(
                f"Invalid institution at row {index}: {error}"
            ) from error
    return validated


class Command(BaseCommand):
    help = "Validate and atomically import the institution catalogue, preserving IDs and review decisions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path", type=Path, default=settings.BASE_DIR / "university.json"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing to the database.",
        )

    def handle(self, *args, **options):
        try:
            payload = json.loads(Path(options["path"]).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CommandError(
                f"Unable to load institution catalogue: {error}"
            ) from error
        records = validate_records(payload)
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        with transaction.atomic():
            existing = {
                item.value: item
                for item in Institution.objects.select_for_update().filter(
                    source=Institution.Source.CATALOGUE
                )
            }
            for value, defaults, review_status in records:
                institution = existing.get(value)
                if institution is None:
                    counts["created"] += 1
                    if not options["dry_run"]:
                        Institution.objects.create(
                            value=value,
                            source=Institution.Source.CATALOGUE,
                            review_status=review_status,
                            **defaults,
                        )
                    continue
                # Retire obsolete records, but never automatically re-approve a
                # record that staff have rejected or left pending review.
                if review_status == Institution.ReviewStatus.REJECTED:
                    defaults["review_status"] = review_status
                changed = [
                    field
                    for field, value in defaults.items()
                    if getattr(institution, field) != value
                ]
                counts["updated" if changed else "unchanged"] += 1
                if changed and not options["dry_run"]:
                    for field in changed:
                        setattr(institution, field, defaults[field])
                    institution.save(update_fields=changed)
        prefix = "Dry run" if options["dry_run"] else "Imported institutions"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}: "
                + ", ".join(f"{count} {kind}" for kind, count in counts.items())
                + "."
            )
        )
