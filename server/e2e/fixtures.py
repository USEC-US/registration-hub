"""Private, exclusively created files for disposable browser fixtures."""

import json
import os
from pathlib import Path


def write_private_fixture(path: Path, payload: dict) -> None:
    # O_EXCL atomically rejects existing paths (including symlinks); permissions
    # apply at creation, before any capability bytes are written.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(payload, stream)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def seed_swiss_browser_fixtures(*, organizer):
    """Real guarded commands in the harness's disposable database only."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from registrations.dev_seed import SeedCatalog, _seed_swiss
    from registrations.models import Registration, RegistrationMember
    from tournaments.models import Game, Tournament, TournamentGame

    now = timezone.now()
    tournament = Tournament.objects.create(
        name="Swiss Journey Test",
        slug="swiss-journey-test",
        students_only=False,
        is_published=True,
    )
    divisions = {}
    for slug, count in (("chess", 9), ("valorant", 16), ("workflow", 9), ("repeat", 4)):
        division = TournamentGame.objects.create(
            tournament=tournament,
            game=Game.objects.create(name=f"swiss-{slug}", slug=f"swiss-{slug}"),
            main_roster_size=1 if slug == "chess" else 2,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=2),
            registration_closes_at=now - timedelta(days=1),
            fee_amount=Decimal("0.00"),
            fee_currency="VND",
        )
        divisions[f"swiss-{slug}"] = division
        if slug in ("workflow", "repeat"):
            for index in range(1, count + 1):
                registration = Registration.objects.create(
                    tournament_game=division,
                    team_name=f"Swiss Team {index}",
                    status="APPROVED",
                    fee_amount_snapshot="0.00",
                    fee_currency_snapshot="VND",
                    contact_email_snapshot=f"private-swiss-{index}@example.invalid",
                )
                for member in range(1, 3):
                    RegistrationMember.objects.create(
                        registration=registration,
                        gamer_tag_snapshot=f"SW-{index}-{member}",
                        is_captain=member == 1,
                        display_order=member,
                    )
    _seed_swiss(
        now=now,
        organizer=organizer,
        catalog=SeedCatalog({tournament.slug: tournament}, divisions),
    )


def seed_lifecycle_browser_fixtures(*, organizer):
    from django.utils import timezone
    from registrations.dev_seed import _seed_lifecycle

    return _seed_lifecycle(now=timezone.now(), organizer=organizer)


def seed_lifecycle_swiss_fixture(*, organizer):
    from django.utils import timezone
    from datetime import timedelta
    from competitions.commands import (
        create_competition,
        configure_elimination,
        select_entrants,
        publish_draw,
    )
    from competitions.swiss_commands import configure_swiss, save_swiss_draw
    from registrations.dev_seed import _upsert_development_team
    from tournaments.models import Tournament, TournamentGame, Game

    now = timezone.now()
    tournament = Tournament.objects.get(slug="dev-usec-lifecycle")
    division = TournamentGame.objects.create(
        tournament=tournament,
        game=Game.objects.create(name="Lifecycle Swiss", slug="lifecycle-swiss"),
        main_roster_size=2,
        substitute_limit=0,
        registration_opens_at=now - timedelta(days=2),
        registration_closes_at=now - timedelta(days=1),
        fee_amount=0,
        fee_currency="VND",
    )
    registrations = [
        _upsert_development_team(
            now=now, organizer=organizer, division=division, team_prefix="LS", index=i
        )
        for i in range(1, 7)
    ]
    competition = create_competition(actor=organizer, tournament_game_id=division.pk)
    configure_swiss(
        actor=organizer,
        competition_id=competition.pk,
        expected_revision=competition.revision,
        name="Swiss",
        format="SWISS_FIXED",
        series_mode="BEST_OF",
        default_series_length=1,
        round_count=3,
        win_target=None,
        loss_limit=None,
        advancement_count=2,
        win_points=3,
        draw_points=1,
        loss_points=0,
        tiebreaks=["OPPONENT_POINTS", "GAME_DIFFERENCE", "GAMES_WON"],
    )
    competition.refresh_from_db()
    configure_elimination(
        actor=organizer,
        competition_id=competition.pk,
        expected_revision=competition.revision,
        stage_sequence=2,
        name="Playoffs",
        format="SINGLE_ELIMINATION",
        default_series_length=1,
    )
    competition.refresh_from_db()
    entrants = select_entrants(
        actor=organizer,
        competition_id=competition.pk,
        expected_revision=competition.revision,
        registration_ids=[r.pk for r in registrations],
    )
    competition.refresh_from_db()
    save_swiss_draw(
        actor=organizer,
        competition_id=competition.pk,
        expected_revision=competition.revision,
        ordered_entrant_ids=[e.pk for e in entrants],
    )
    competition.refresh_from_db()
    publish_draw(
        actor=organizer,
        competition_id=competition.pk,
        expected_revision=competition.revision,
    )
