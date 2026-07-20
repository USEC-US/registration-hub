from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from tournaments.models import Game, Tournament, TournamentGame

PLAYER_EMAIL = "player@email.com"
ORGANIZER_EMAIL = "organizer@email.com"
ADMIN_EMAIL = "admin@email.com"

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
    gamer_tag: str,
    school: str,
    is_staff: bool,
    is_superuser: bool,
    groups: tuple[Group, ...],
):
    user_model = get_user_model()
    user, _ = user_model.objects.update_or_create(
        email=email,
        defaults={
            "gamer_tag": gamer_tag,
            "school": school,
            "is_active": True,
            "is_staff": is_staff,
            "is_superuser": is_superuser,
        },
    )
    user.set_password(password)
    user.save(
        update_fields=(
            "password",
            "gamer_tag",
            "school",
            "is_active",
            "is_staff",
            "is_superuser",
        )
    )
    user.groups.set(groups)
    return user


def _seed_accounts():
    organizers = Group.objects.get(name="Organizers")
    player = _set_account(
        email=PLAYER_EMAIL,
        password="player@123",
        gamer_tag="Rookie",
        school="HCMUS",
        is_staff=False,
        is_superuser=False,
        groups=(),
    )
    organizer = _set_account(
        email=ORGANIZER_EMAIL,
        password="organizer@123",
        gamer_tag="",
        school="",
        is_staff=True,
        is_superuser=False,
        groups=(organizers,),
    )
    admin = _set_account(
        email=ADMIN_EMAIL,
        password="admin@123",
        gamer_tag="",
        school="",
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
        "rocket-league": _upsert_game(
            slug="rocket-league", name="Rocket League"
        ),
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


def seed_development_data(*, now: datetime) -> DevelopmentSeedResult:
    accounts = _seed_accounts()
    catalog = _seed_catalog(now=now)
    return DevelopmentSeedResult(
        account_emails=tuple(account.email for account in accounts),
        tournament_slugs=tuple(catalog.tournaments),
        registration_ids=(),
    )
