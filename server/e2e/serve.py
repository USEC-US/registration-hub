"""Run Django for browser tests with a disposable PostgreSQL database and media."""

import json
import os
import secrets
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DEBUG"] = "true"
os.environ["TURNSTILE_SECRET_KEY"] = ""
os.environ["DJANGO_ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://127.0.0.1:4175"
os.environ["CSRF_ALLOWED_ORIGINS"] = "http://127.0.0.1:4175"


def seed():
    from datetime import timedelta

    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from django.core.management import call_command
    from django.utils import timezone

    from accounts.models import Institution
    from tournaments.models import Game, Tournament, TournamentGame
    from registrations.models import PaymentSettings, Registration
    from rest_framework.test import APIClient

    PaymentSettings.objects.update_or_create(
        pk=1,
        defaults={
            "enabled": True,
            "bank_name": "TEST ONLY - DO NOT TRANSFER",
            "bank_bin": "970436",
            "account_number": "000000000000",
            "account_holder": "FICTIONAL BROWSER FIXTURE",
            "payment_hold_minutes": 60,
        },
    )

    institution = Institution.objects.create(
        source="CATALOGUE",
        value="e2e-school",
        label="Journey Test University",
        review_status="VERIFIED",
    )
    user_model = get_user_model()
    user_model.objects.create_user(
        email="journey-player@example.test",
        password="Journey-test-password-2026",
        first_name="Journey",
        last_name="Player",
        institution=institution,
    )
    call_command("bootstrap_organizers", verbosity=0)
    organizer = user_model.objects.create_user(
        email="journey-organizer@example.test",
        password="Journey-test-password-2026",
        first_name="Journey",
        last_name="Organizer",
        is_staff=True,
        student_id="E2E-ORGANIZER",
    )
    organizer.groups.add(Group.objects.get(name="Organizers"))
    tournament = Tournament.objects.create(
        name="Registration Journey Test",
        slug="registration-journey-test",
        students_only=True,
        is_published=True,
    )
    for slug, minimum, maximum, fee in (
        ("team-free", 2, 3, "0.00"),
        ("solo-free", 1, 1, "0.00"),
        ("solo-paid", 1, 1, "50000.00"),
    ):
        game = Game.objects.create(name=slug, slug=slug)
        division = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=minimum,
            substitute_limit=maximum - minimum,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            registration_capacity=100,
            fee_amount=fee,
            fee_currency="VND",
        )

        if slug == "solo-paid":
            credential = secrets.token_hex(32)
            response = APIClient().post(
                "/api/registrations/submit/",
                {
                    "tournament_game": division.pk,
                    "team_name": "",
                    "team_tag": "",
                    "submitter_role": "captain",
                    "contact_facebook_snapshot": "https://facebook.com/journey-captain",
                    "contact_phone_snapshot": "+84901234567",
                    "turnstile_token": "test-only",
                    "members": [
                        {
                            "first_name_snapshot": "Expired",
                            "last_name_snapshot": "Fixture",
                            "date_of_birth_snapshot": "2005-01-01",
                            "student_id_snapshot": "EXPIRED001",
                            "gamer_tag_snapshot": "Expired#ONE",
                            "institution_id": institution.pk,
                            "is_captain": True,
                            "roster_role": "main",
                            "display_order": 1,
                        }
                    ],
                },
                format="json",
                HTTP_X_REGISTRATION_ACCESS=credential,
            )
            if response.status_code != 201:
                raise RuntimeError(
                    f"Expired fixture submission failed: {response.data}"
                )
            registration_id = response.data["id"]
            # Only this disposable fixture changes Django's deadline; production API has no hook.
            Registration.objects.filter(pk=registration_id).update(
                payment_due_at=timezone.now() - timedelta(seconds=1)
            )
            fixture_path = Path("/tmp/hcmusec-registration-journey-fixture.json")
            fixture_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "gameId": division.pk,
                        "credential": credential,
                        "attemptState": "submitted",
                        "registrationId": registration_id,
                    }
                )
            )
            fixture_path.chmod(0o600)


def main():
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection, connections

    # A unique name prevents reuse, flushing, or deletion of a developer's database.
    database_name = f"test_registration_journey_{uuid4().hex[:12]}"
    connection.settings_dict["TEST"]["NAME"] = database_name
    original_name = connection.settings_dict["NAME"]
    created = False

    def stop(_signal, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with TemporaryDirectory(prefix="registration-journey-media-") as media:
        settings.MEDIA_ROOT = Path(media)
        try:
            connection.creation.create_test_db(verbosity=0, autoclobber=False)
            created = True
            seed()
            print(f"Browser fixture database ready: {database_name}", flush=True)
            call_command("runserver", "127.0.0.1:8015", use_reloader=False)
        finally:
            Path("/tmp/hcmusec-registration-journey-fixture.json").unlink(
                missing_ok=True
            )
            connections.close_all()
            if created or connection.settings_dict["NAME"] == database_name:
                connection.creation.destroy_test_db(original_name, verbosity=0)


if __name__ == "__main__":
    main()
