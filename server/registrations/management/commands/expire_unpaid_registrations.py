from django.core.management.base import BaseCommand
from registrations.reservations import expire_due_registrations


class Command(BaseCommand):
    help = "Release overdue unpaid reservations (schedule every minute)."

    def add_arguments(self, parser):
        parser.add_argument("--division", type=int)

    def handle(self, *args, **options):
        count = expire_due_registrations(division_id=options["division"])
        self.stdout.write(f"Expired {count} registration(s).")
