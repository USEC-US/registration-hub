from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

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


def seed_development_data(*, now: datetime) -> DevelopmentSeedResult:
    del now
    accounts = _seed_accounts()
    return DevelopmentSeedResult(
        account_emails=tuple(account.email for account in accounts),
        tournament_slugs=(),
        registration_ids=(),
    )
