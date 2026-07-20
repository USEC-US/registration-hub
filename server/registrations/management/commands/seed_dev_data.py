from io import StringIO

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from registrations.dev_seed import ACCOUNT_CREDENTIALS, seed_development_data


class Command(BaseCommand):
    help = "Create or restore deterministic development accounts and tournament data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-non-debug",
            action="store_true",
            help="Allow predictable development credentials while DEBUG=False.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError(
                "seed_dev_data creates predictable credentials and refuses to run "
                "while DEBUG=False. Pass --allow-non-debug only for an intentional "
                "non-production test database."
            )

        now = timezone.now()
        try:
            with transaction.atomic():
                call_command("bootstrap_organizers", stdout=StringIO())
                result = seed_development_data(now=now)
        except (IntegrityError, PermissionDenied, ValidationError) as error:
            raise CommandError(f"Development seed failed: {error}") from error

        self.stdout.write(self.style.SUCCESS("Development seed data is ready."))
        self.stdout.write("Accounts:")
        for role, email, password in ACCOUNT_CREDENTIALS:
            self.stdout.write(f"  {role}: {email} / {password}")
        if result.tournament_slugs:
            self.stdout.write("Tournaments:")
            for slug in result.tournament_slugs:
                self.stdout.write(f"  {slug}")
        self.stdout.write(
            "Rerunning restores command-owned accounts and development scenarios."
        )
