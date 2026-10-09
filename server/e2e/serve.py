"""Run Django for browser tests with a disposable PostgreSQL database and media."""

import os
import secrets
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from e2e.fixtures import write_private_fixture

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DEBUG"] = "true"
os.environ["TURNSTILE_SECRET_KEY"] = ""
os.environ["DJANGO_ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://127.0.0.1:4175"
os.environ["CSRF_ALLOWED_ORIGINS"] = "http://127.0.0.1:4175"


def seed():
    from datetime import timedelta
    from decimal import Decimal

    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from django.core.management import call_command
    from django.utils import timezone

    from accounts.models import Institution
    from competitions.commands import (
        apply_correction,
        configure_elimination,
        create_competition,
        finalize_match,
        preview_correction,
        publish_draw,
        save_elimination_draw,
        schedule_match,
        select_entrants,
    )
    from competitions.models import Match
    from registrations.models import (
        PaymentSettings,
        Registration,
        RegistrationMember,
    )
    from tournaments.models import Game, Tournament, TournamentGame
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
    from registrations.dev_seed import SeedCatalog, _seed_round_robin

    rr_tournament = Tournament.objects.create(
        name="Round Robin Journey Test",
        slug="round-robin-journey-test",
        students_only=False,
        is_published=True,
    )
    rr_divisions = {}
    for slug, key in (
        ("rr-fixed", "round-robin-valorant"),
        ("rr-double", "round-robin-league-of-legends"),
        ("rr-workflow", "workflow"),
    ):
        division = TournamentGame.objects.create(
            tournament=rr_tournament,
            game=Game.objects.create(name=slug, slug=slug),
            main_roster_size=2,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=2),
            registration_closes_at=timezone.now() - timedelta(days=1),
            fee_amount=Decimal("0.00"),
            fee_currency="VND",
        )
        rr_divisions[key] = division
        if key == "workflow":
            for index in range(1, 4):
                registration = Registration.objects.create(
                    tournament_game=division,
                    team_name=f"RR Team {index}",
                    status="APPROVED",
                    fee_amount_snapshot="0.00",
                    fee_currency_snapshot="VND",
                )
                for member in range(1, 3):
                    RegistrationMember.objects.create(
                        registration=registration,
                        gamer_tag_snapshot=f"RR-{index}-Player-{member}",
                        display_order=member,
                        is_captain=member == 1,
                    )
    _seed_round_robin(
        now=timezone.now(),
        organizer=organizer,
        catalog=SeedCatalog({rr_tournament.slug: rr_tournament}, rr_divisions),
    )
    double_tournament = Tournament.objects.create(
        name="Double Elimination Journey Test",
        slug="double-elimination-journey-test",
        students_only=False,
        is_published=True,
    )
    for slug, entrant_count, policy in (
        ("double-reset", 4, "RESET"),
        ("double-public", 4, "NO_RESET"),
        ("double-large", 16, "RESET"),
        ("double-two", 2, "NO_RESET"),
    ):
        division = TournamentGame.objects.create(
            tournament=double_tournament,
            game=Game.objects.create(name=slug, slug=slug),
            main_roster_size=2,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=2),
            registration_closes_at=timezone.now() - timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        registrations = []
        for index in range(1, entrant_count + 1):
            registration = Registration.objects.create(
                tournament_game=division,
                team_name=f"DE Team {index}",
                status=Registration.Status.APPROVED,
                contact_email_snapshot=f"private-de-{index}@example.invalid",
                fee_amount_snapshot="0.00",
                fee_currency_snapshot="VND",
            )
            for member in range(1, 3):
                RegistrationMember.objects.create(
                    registration=registration,
                    gamer_tag_snapshot=f"DE-{index}-Player-{member}",
                    is_captain=member == 1,
                    display_order=member,
                )
            registrations.append(registration)
        if slug != "double-reset":
            competition = create_competition(
                actor=organizer, tournament_game_id=division.pk
            )
            configure_elimination(
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
                name="Public browser bracket",
                format="DOUBLE_ELIMINATION",
                grand_final_policy=policy,
                default_series_length=1,
            )
            competition.refresh_from_db()
            entrants = select_entrants(
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
                registration_ids=[registration.pk for registration in registrations],
            )
            competition.refresh_from_db()
            save_elimination_draw(
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
                entrant_order=[entrant.pk for entrant in entrants],
            )
            competition.refresh_from_db()
            publish_draw(
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
            )

    tournament = Tournament.objects.create(
        name="Registration Journey Test",
        slug="registration-journey-test",
        students_only=True,
        is_published=True,
    )
    divisions = {}
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
        divisions[slug] = division

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
            write_private_fixture(
                fixture_path,
                {
                    "version": 1,
                    "gameId": division.pk,
                    "credential": credential,
                    "attemptState": "submitted",
                    "registrationId": registration_id,
                },
            )

            bracket_registrations = []
            for index in range(1, 4):
                registration = Registration.objects.create(
                    tournament_game=divisions["solo-free"],
                    status=Registration.Status.APPROVED,
                    fee_amount_snapshot="0.00",
                    fee_currency_snapshot="VND",
                )
                RegistrationMember.objects.create(
                    registration=registration,
                    gamer_tag_snapshot=f"Bracket Player {index}",
                    is_captain=True,
                    display_order=1,
                )
                bracket_registrations.append(registration)

            competition = create_competition(
                actor=organizer,
                tournament_game_id=divisions["solo-free"].pk,
            )
            configure_elimination(
                format="SINGLE_ELIMINATION",
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
                name="Journey final bracket",
                default_series_length=3,
            )
            competition.refresh_from_db()
            entrants = select_entrants(
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
                registration_ids=[item.pk for item in bracket_registrations],
            )
            competition.refresh_from_db()
            draw = save_elimination_draw(
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
                entrant_order=[item.pk for item in entrants],
            )
            competition.refresh_from_db()
            publish_draw(
                actor=organizer,
                competition_id=competition.pk,
                expected_revision=competition.revision,
            )
            competition.refresh_from_db()
            semifinal = draw.rounds.get(number=1).matches.get(number=2)
            final = draw.rounds.get(number=2).matches.get(number=1)
            schedule_match(
                actor=organizer,
                match_id=semifinal.pk,
                expected_revision=competition.revision,
                scheduled_at=timezone.now() + timedelta(days=1),
            )
            competition.refresh_from_db()
            finalize_match(
                actor=organizer,
                match_id=semifinal.pk,
                expected_revision=competition.revision,
                outcome=Match.Outcome.PLAYED,
                side_one_score=2,
                side_two_score=0,
            )
            competition.refresh_from_db()
            finalize_match(
                actor=organizer,
                match_id=final.pk,
                expected_revision=competition.revision,
                outcome=Match.Outcome.PLAYED,
                side_one_score=0,
                side_two_score=2,
            )
            competition.refresh_from_db()
            correction = preview_correction(
                actor=organizer,
                match_id=semifinal.pk,
                expected_revision=competition.revision,
                outcome=Match.Outcome.PLAYED,
                side_one_score=0,
                side_two_score=2,
            )
            apply_correction(
                actor=organizer,
                token=correction["token"],
                internal_reason="Browser-only correction fixture.",
            )
            competition.refresh_from_db()
            finalize_match(
                actor=organizer,
                match_id=final.pk,
                expected_revision=competition.revision,
                outcome=Match.Outcome.PLAYED,
                side_one_score=2,
                side_two_score=0,
            )
            return fixture_path


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
    fixture_path = None

    def stop(_signal, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with TemporaryDirectory(prefix="registration-journey-media-") as media:
        settings.MEDIA_ROOT = Path(media)
        try:
            connection.creation.create_test_db(verbosity=0, autoclobber=False)
            created = True
            fixture_path = seed()
            print(f"Browser fixture database ready: {database_name}", flush=True)
            call_command("runserver", "127.0.0.1:8015", use_reloader=False)
        finally:
            if fixture_path is not None:
                fixture_path.unlink(missing_ok=True)
            connections.close_all()
            if created or connection.settings_dict["NAME"] == database_name:
                connection.creation.destroy_test_db(original_name, verbosity=0)


if __name__ == "__main__":
    main()
