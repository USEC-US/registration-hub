from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from registrations.bank_catalogue import BankCatalogueError, sync_bank_catalogue


class Command(BaseCommand):
    help = "Refresh the local bank catalogue from the public VietQR.io API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", type=Path, help="Import a saved API JSON response instead."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and preview without saving.",
        )

    def handle(self, *args, **options):
        try:
            payload = options["file"].read_bytes() if options["file"] else None
            result = sync_bank_catalogue(payload, dry_run=options["dry_run"])
        except (BankCatalogueError, OSError) as error:
            raise CommandError(str(error)) from error
        prefix = "Dry run" if options["dry_run"] else "Bank catalogue refreshed"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}: {result['created']} new, {result['updated']} refreshed, "
                f"{result['deactivated']} inactive."
            )
        )
