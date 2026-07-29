from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.models import Institution
from tournaments.models import Game, Tournament, TournamentGame

from .models import PaymentAttempt, Registration, RegistrationStatusEvent
from .services import (
    RegistrationMemberInput,
    approve_registration,
    reject_registration,
    review_payment_attempt,
    start_review,
    submit_payment_attempt,
    submit_registration,
)

PLAYER_EMAIL = "player@email.com"
ORGANIZER_EMAIL = "organizer@email.com"
ADMIN_EMAIL = "admin@email.com"
HCMUS_INSTITUTION_VALUE = "222"

ACCOUNT_CREDENTIALS = (
    ("Player", PLAYER_EMAIL, "player@123"),
    ("Organizer", ORGANIZER_EMAIL, "organizer@123"),
    ("Admin", ADMIN_EMAIL, "admin@123"),
)

SEED_TOURNAMENT_SLUGS = (
    "dev-usec-current",
    "dev-usec-archive",
    "dev-usec-draft",
)

SCENARIO_SUMMARY = (
    "Valorant: SUBMITTED / payment PENDING",
    "Chess: APPROVED / free registration",
    "Counter-Strike 2: UNDER_REVIEW / payment VERIFIED / capacity FULL",
    "Rocket League: REJECTED / rejected payment plus pending replacement",
    "League of Legends: registration NOT_OPEN",
    "Development draft: unpublished",
)


@dataclass(frozen=True)
class DevelopmentSeedResult:
    account_emails: tuple[str, ...]
    tournament_slugs: tuple[str, ...]
    registration_ids: tuple[int, ...]


@dataclass(frozen=True)
class SeedCatalog:
    tournaments: dict[str, Tournament]
    tournament_games: dict[str, TournamentGame]


def _set_account(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    institution: Institution | None,
    is_staff: bool,
    is_superuser: bool,
    groups: tuple[Group, ...],
):
    user_model = get_user_model()
    user, _ = user_model.objects.update_or_create(
        email=email,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "institution": institution,
            "is_active": True,
            "is_staff": is_staff,
            "is_superuser": is_superuser,
        },
    )
    user.set_password(password)
    user.save(
        update_fields=(
            "password",
            "first_name",
            "last_name",
            "institution",
            "is_active",
            "is_staff",
            "is_superuser",
        )
    )
    user.groups.set(groups)
    return user


def _seed_player_institution() -> Institution:
    institution, _ = Institution.objects.get_or_create(
        source=Institution.Source.CATALOGUE,
        value=HCMUS_INSTITUTION_VALUE,
        defaults={
            "label": "University of Science",
            "code": "QST",
            "short_name": "HCMUS",
            "english_name": "University of Science - VNU",
            "type": "National university",
            "location": "Ho Chi Minh City",
            "review_status": Institution.ReviewStatus.VERIFIED,
        },
    )
    return institution


def _seed_accounts():
    organizers = Group.objects.get(name="Organizers")
    player_institution = _seed_player_institution()
    player = _set_account(
        email=PLAYER_EMAIL,
        password="player@123",
        first_name="Development",
        last_name="Player",
        institution=player_institution,
        is_staff=False,
        is_superuser=False,
        groups=(),
    )
    organizer = _set_account(
        email=ORGANIZER_EMAIL,
        password="organizer@123",
        first_name="Development",
        last_name="Organizer",
        institution=None,
        is_staff=True,
        is_superuser=False,
        groups=(organizers,),
    )
    admin = _set_account(
        email=ADMIN_EMAIL,
        password="admin@123",
        first_name="Development",
        last_name="Administrator",
        institution=None,
        is_staff=True,
        is_superuser=True,
        groups=(),
    )
    return player, organizer, admin


def _upsert_game(*, slug: str, name: str) -> Game:
    game, _ = Game.objects.update_or_create(
        slug=slug,
        defaults={"name": name, "is_active": True},
    )
    return game


def _upsert_tournament_game(
    *,
    tournament: Tournament,
    game: Game,
    team_size_min: int,
    team_size_max: int,
    registration_opens_at: datetime,
    registration_closes_at: datetime,
    registration_capacity: int | None,
    fee_amount: Decimal,
) -> TournamentGame:
    tournament_game, _ = TournamentGame.objects.update_or_create(
        tournament=tournament,
        game=game,
        defaults={
            "team_size_min": team_size_min,
            "team_size_max": team_size_max,
            "registration_opens_at": registration_opens_at,
            "registration_closes_at": registration_closes_at,
            "registration_capacity": registration_capacity,
            "fee_amount": fee_amount,
            "fee_currency": "VND",
        },
    )
    return tournament_game


def _seed_catalog(*, now: datetime) -> SeedCatalog:
    games = {
        "valorant": _upsert_game(slug="valorant", name="Valorant"),
        "chess": _upsert_game(slug="chess", name="Chess"),
        "counter-strike-2": _upsert_game(
            slug="counter-strike-2", name="Counter-Strike 2"
        ),
        "league-of-legends": _upsert_game(
            slug="league-of-legends", name="League of Legends"
        ),
        "rocket-league": _upsert_game(slug="rocket-league", name="Rocket League"),
        "ea-sports-fc": _upsert_game(slug="ea-sports-fc", name="EA Sports FC"),
    }

    current, _ = Tournament.objects.update_or_create(
        slug="dev-usec-current",
        defaults={
            "name": "USEC Development Open",
            "description": "Current development scenarios for registration testing.",
            "starts_at": now + timedelta(days=14),
            "ends_at": now + timedelta(days=15),
            "location": "HCMUS",
            "is_published": True,
        },
    )
    archive, _ = Tournament.objects.update_or_create(
        slug="dev-usec-archive",
        defaults={
            "name": "USEC Development Archive",
            "description": "Historical development scenarios with closed registration.",
            "starts_at": now - timedelta(days=60),
            "ends_at": now - timedelta(days=59),
            "location": "HCMUS",
            "is_published": True,
        },
    )
    draft, _ = Tournament.objects.update_or_create(
        slug="dev-usec-draft",
        defaults={
            "name": "USEC Development Draft",
            "description": "Unpublished development tournament for visibility testing.",
            "starts_at": now + timedelta(days=30),
            "ends_at": now + timedelta(days=31),
            "location": "HCMUS",
            "is_published": False,
        },
    )

    tournament_games = {
        "valorant": _upsert_tournament_game(
            tournament=current,
            game=games["valorant"],
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=16,
            fee_amount=Decimal("50000.00"),
        ),
        "chess": _upsert_tournament_game(
            tournament=current,
            game=games["chess"],
            team_size_min=1,
            team_size_max=1,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=None,
            fee_amount=Decimal("0.00"),
        ),
        "counter-strike-2": _upsert_tournament_game(
            tournament=current,
            game=games["counter-strike-2"],
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=1,
            fee_amount=Decimal("75000.00"),
        ),
        "league-of-legends": _upsert_tournament_game(
            tournament=current,
            game=games["league-of-legends"],
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=now + timedelta(days=2),
            registration_closes_at=now + timedelta(days=10),
            registration_capacity=8,
            fee_amount=Decimal("100000.00"),
        ),
        "rocket-league": _upsert_tournament_game(
            tournament=archive,
            game=games["rocket-league"],
            team_size_min=3,
            team_size_max=3,
            registration_opens_at=now - timedelta(days=75),
            registration_closes_at=now - timedelta(days=61),
            registration_capacity=8,
            fee_amount=Decimal("60000.00"),
        ),
        "ea-sports-fc": _upsert_tournament_game(
            tournament=draft,
            game=games["ea-sports-fc"],
            team_size_min=1,
            team_size_max=1,
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=14),
            registration_capacity=32,
            fee_amount=Decimal("30000.00"),
        ),
    }
    return SeedCatalog(
        tournaments={
            current.slug: current,
            archive.slug: archive,
            draft.slug: draft,
        },
        tournament_games=tournament_games,
    )


def _member_inputs(
    roster: tuple[tuple[str, str], ...],
) -> tuple[RegistrationMemberInput, ...]:
    return tuple(
        RegistrationMemberInput(
            gamer_tag_snapshot=gamer_tag,
            school_snapshot=school,
            is_captain=index == 1,
            display_order=index,
        )
        for index, (gamer_tag, school) in enumerate(roster, start=1)
    )


def _set_scenario_times(
    *,
    registration: Registration,
    submitted_at: datetime,
    event_times: tuple[datetime, ...],
    payment_times: tuple[datetime, ...],
) -> None:
    events = list(registration.status_events.order_by("pk"))
    payments = list(registration.payment_attempts.order_by("pk"))
    if len(events) != len(event_times):
        raise ValueError(
            f"Expected {len(event_times)} events for registration {registration.pk}; "
            f"found {len(events)}."
        )
    if len(payments) != len(payment_times):
        raise ValueError(
            f"Expected {len(payment_times)} payments for registration {registration.pk}; "
            f"found {len(payments)}."
        )

    last_activity = max((submitted_at, *event_times, *payment_times))
    Registration.objects.filter(pk=registration.pk).update(
        submitted_at=submitted_at,
        created_at=submitted_at,
        updated_at=last_activity,
    )
    for event, created_at in zip(events, event_times, strict=True):
        RegistrationStatusEvent.objects.filter(pk=event.pk).update(
            created_at=created_at
        )
    for payment, created_at in zip(payments, payment_times, strict=True):
        updates = {"created_at": created_at}
        if payment.reviewed_at is not None:
            updates["reviewed_at"] = created_at + timedelta(hours=2)
        PaymentAttempt.objects.filter(pk=payment.pk).update(**updates)


def _rebuild_registrations(
    *,
    now: datetime,
    player,
    organizer,
    catalog: SeedCatalog,
) -> tuple[Registration, ...]:
    Registration.objects.filter(
        submitted_by=player,
        tournament_game__tournament__slug__in=SEED_TOURNAMENT_SLUGS,
    ).delete()

    valorant = submit_registration(
        submitted_by=player,
        tournament_game_id=catalog.tournament_games["valorant"].pk,
        team_name="Blue Phoenix",
        members=_member_inputs(
            (
                ("Rookie", "HCMUS"),
                ("Astra", "HCMUT"),
                ("Cipher", "UIT"),
                ("Lotus", "UEH"),
                ("Nova", "VNUHCM-US"),
            )
        ),
    )
    submit_payment_attempt(
        actor=player,
        registration_id=valorant.pk,
        amount=Decimal("50000.00"),
        currency="VND",
        reference="DEV-VAL-PENDING",
    )

    chess = submit_registration(
        submitted_by=player,
        tournament_game_id=catalog.tournament_games["chess"].pk,
        team_name="",
        members=_member_inputs((("Rookie", "HCMUS"),)),
    )
    start_review(
        actor=organizer,
        registration_id=chess.pk,
        note="Seeded organizer review.",
    )
    approve_registration(
        actor=organizer,
        registration_id=chess.pk,
        note="Seeded approval.",
    )

    counter_strike = submit_registration(
        submitted_by=player,
        tournament_game_id=catalog.tournament_games["counter-strike-2"].pk,
        team_name="Campus Five",
        members=_member_inputs(
            (
                ("Rookie", "HCMUS"),
                ("Aster", "HCMUT"),
                ("Bolt", "UIT"),
                ("Drift", "UEH"),
                ("Echo", "VNUHCM-US"),
            )
        ),
    )
    counter_strike_payment = submit_payment_attempt(
        actor=player,
        registration_id=counter_strike.pk,
        amount=Decimal("75000.00"),
        currency="VND",
        reference="DEV-CS2-VERIFIED",
    )
    review_payment_attempt(
        actor=organizer,
        payment_attempt_id=counter_strike_payment.pk,
        status=PaymentAttempt.Status.VERIFIED,
        note="Reference confirmed for the development scenario.",
    )
    start_review(
        actor=organizer,
        registration_id=counter_strike.pk,
        note="Eligibility review in progress.",
    )

    rocket_game = catalog.tournament_games["rocket-league"]
    final_rocket_opens_at = rocket_game.registration_opens_at
    final_rocket_closes_at = rocket_game.registration_closes_at
    TournamentGame.objects.filter(pk=rocket_game.pk).update(
        registration_opens_at=now - timedelta(hours=1),
        registration_closes_at=now + timedelta(hours=1),
    )
    rocket_game.refresh_from_db(
        fields=("registration_opens_at", "registration_closes_at")
    )
    rocket_league = submit_registration(
        submitted_by=player,
        tournament_game_id=rocket_game.pk,
        team_name="Orbit Three",
        members=_member_inputs(
            (
                ("Rookie", "HCMUS"),
                ("Comet", "HCMUT"),
                ("Vector", "UIT"),
            )
        ),
    )
    rejected_payment = submit_payment_attempt(
        actor=player,
        registration_id=rocket_league.pk,
        amount=Decimal("60000.00"),
        currency="VND",
        reference="DEV-RL-REJECTED",
    )
    review_payment_attempt(
        actor=organizer,
        payment_attempt_id=rejected_payment.pk,
        status=PaymentAttempt.Status.REJECTED,
        note="Reference could not be verified.",
    )
    submit_payment_attempt(
        actor=player,
        registration_id=rocket_league.pk,
        amount=Decimal("60000.00"),
        currency="VND",
        reference="DEV-RL-REPLACEMENT",
    )
    start_review(
        actor=organizer,
        registration_id=rocket_league.pk,
        note="Historical eligibility review.",
    )
    reject_registration(
        actor=organizer,
        registration_id=rocket_league.pk,
        note="Eligibility documents were incomplete.",
    )
    TournamentGame.objects.filter(pk=rocket_game.pk).update(
        registration_opens_at=final_rocket_opens_at,
        registration_closes_at=final_rocket_closes_at,
    )
    rocket_game.registration_opens_at = final_rocket_opens_at
    rocket_game.registration_closes_at = final_rocket_closes_at

    _set_scenario_times(
        registration=valorant,
        submitted_at=now - timedelta(days=4),
        event_times=(now - timedelta(days=4),),
        payment_times=(now - timedelta(days=3),),
    )
    _set_scenario_times(
        registration=chess,
        submitted_at=now - timedelta(days=6),
        event_times=(
            now - timedelta(days=6),
            now - timedelta(days=5),
            now - timedelta(days=4),
        ),
        payment_times=(),
    )
    _set_scenario_times(
        registration=counter_strike,
        submitted_at=now - timedelta(days=3),
        event_times=(now - timedelta(days=3), now - timedelta(days=2)),
        payment_times=(now - timedelta(days=3) + timedelta(hours=1),),
    )
    _set_scenario_times(
        registration=rocket_league,
        submitted_at=now - timedelta(days=70),
        event_times=(
            now - timedelta(days=70),
            now - timedelta(days=69),
            now - timedelta(days=68),
        ),
        payment_times=(
            now - timedelta(days=69, hours=12),
            now - timedelta(days=68, hours=12),
        ),
    )

    return valorant, chess, counter_strike, rocket_league


def seed_development_data(*, now: datetime) -> DevelopmentSeedResult:
    player, organizer, admin = _seed_accounts()
    catalog = _seed_catalog(now=now)
    registrations = _rebuild_registrations(
        now=now,
        player=player,
        organizer=organizer,
        catalog=catalog,
    )
    return DevelopmentSeedResult(
        account_emails=(player.email, organizer.email, admin.email),
        tournament_slugs=tuple(catalog.tournaments),
        registration_ids=tuple(registration.pk for registration in registrations),
    )
