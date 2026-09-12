import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.management.commands.import_institutions import validate_records
from accounts.services.catalogue import build_catalogue


class Command(BaseCommand):
    help = "Build university.json and a review report from pinned MOET/SWOT source snapshots (no DB writes)."
    requires_system_checks = []

    def add_arguments(self, parser):
        root = settings.BASE_DIR / "data" / "institutions"
        parser.add_argument("--sources", type=Path, default=root)
        parser.add_argument(
            "--base",
            type=Path,
            help="Previous catalogue when updating sources; defaults to the pinned legacy snapshot.",
        )
        parser.add_argument(
            "--output", type=Path, default=settings.BASE_DIR / "university.json"
        )
        parser.add_argument("--report", type=Path, default=root / "review.json")

    def handle(self, *args, **options):
        root = options["sources"]
        try:

            def read(path):
                return json.loads(path.read_text(encoding="utf-8"))

            base = read(options["base"] or root / "legacy.json")
            moet = read(root / "moet.json")
            swot = read(root / "swot.json")
            overrides = read(root / "overrides.json")
            if len(moet["data"]) != moet["count"]:
                raise ValueError("MOET snapshot is incomplete")
            records, report = build_catalogue(
                base["data"], moet["data"], swot["data"], overrides, swot["revision"]
            )
            payload = {
                "status": True,
                "message": "Curated institution catalogue",
                "sources": {
                    "moet": {k: v for k, v in moet.items() if k != "data"},
                    "swot": {k: v for k, v in swot.items() if k != "data"},
                },
                "data": records,
            }
            validate_records(payload)
            report["records"] = len(records)
            report["retired"] = overrides.get("retired", {})
            report["legacy_only"] = [
                {"value": r["value"], "label": r["label"]}
                for r in records
                if r.get("review_status") != "REJECTED"
                and all(p["source"] == "legacy" for p in r["provenance"])
            ]
            report["notes"] = [
                "Unresolved SWOT entries are candidates, not imported additions.",
                "Legacy-only entries retain their previous names/locations; they are not newly verified by MOET.",
                "Province metadata from the legacy source has not been updated for the 2025 reforms.",
                "VERIFIED means accepted for this picker; it is not accreditation or proof of a user's affiliation.",
            ]
        except (OSError, UnicodeError, ValueError, KeyError) as error:
            raise CommandError(f"Unable to build catalogue: {error}") from error
        for path, data in ((options["output"], payload), (options["report"], report)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        self.stdout.write(
            f"Built {len(records)} records; {len(report['unresolved'])} SWOT candidates held for review."
        )
