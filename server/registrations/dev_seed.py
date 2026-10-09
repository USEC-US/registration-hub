from contextlib import contextmanager
from datetime import date
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageDraw

from accounts.models import Institution
from accounts.services.institutions import normalize_institution_label
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
    set_round_series_length,
    save_match_progress,
)
from competitions.models import Competition, Match, Round, Stage, StageDraw
from competitions.round_robin_commands import (
    configure_round_robin,
    save_round_robin_draw,
    group_standings,
    preview_group_tie,
    confirm_group_tie,
)
from tournaments.models import Game, Tournament, TournamentGame

from .models import (
    PaymentAttempt,
    PaymentIntent,
    PaymentSettings,
    Registration,
    RegistrationMember,
    RegistrationStatusEvent,
)
from .services import (
    RegistrationMemberInput,
    approve_registration,
    reject_registration,
    review_payment_attempt,
    start_review,
    submit_payment_attempt,
    submit_registration,
)


def _sample_payment_image():
    image = Image.new("RGB", (360, 100), "white")
    ImageDraw.Draw(image).text(
        (20, 40), "DEVELOPMENT SAMPLE - NOT A PAYMENT", fill="black"
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return ContentFile(output.getvalue(), name="development-sample.png")


PLAYER_EMAIL = "player@email.com"
ORGANIZER_EMAIL = "organizer@email.com"
ADMIN_EMAIL = "admin@email.com"
HCMUS_INSTITUTION_VALUE = "222"

ACCOUNT_CREDENTIALS = (
    ("Player", PLAYER_EMAIL, "player@123"),
    ("Organizer", ORGANIZER_EMAIL, "organizer@123"),
    ("Admin", ADMIN_EMAIL, "admin@123"),
)

BRACKET_TOURNAMENT_SLUGS = (
    "dev-sponsor-open",
    "dev-sponsor-arena",
    "dev-sponsor-expired",
    "dev-fpt-shop-uni-tour-2026",
)

SEED_TOURNAMENT_SLUGS = (
    "dev-usec-current",
    "dev-usec-archive",
    "dev-usec-draft",
    *BRACKET_TOURNAMENT_SLUGS,
    "dev-usec-double-elimination",
)

SCENARIO_SUMMARY = (
    "Valorant: SUBMITTED / payment PENDING",
    "Chess: APPROVED / free registration",
    "Counter-Strike 2: UNDER_REVIEW / payment VERIFIED / capacity FULL",
    "Rocket League: REJECTED / rejected payment plus pending replacement",
    "League of Legends: registration NOT_OPEN",
    "Chess: published five-player single-elimination bracket",
    "Development draft: unpublished",
    "Publisher open: 8-team paid Valorant/League of Legends divisions",
    "Publisher arena: 8-team free Arena of Valor division",
    "Publisher archive: 8-team divisions, all registration expired",
    "League of Legends: published eight-team single-elimination bracket",
    "FPT Shop Uni Tour 2026: synthetic 16-team LQM bracket (BO1 early, BO3 finals)",
    "Double elimination: ready 16-team reset / completed 5-team no-reset brackets",
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
    student_id: str,
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
            "student_id": student_id,
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
            "student_id",
            "is_active",
            "is_staff",
            "is_superuser",
        )
    )
    user.groups.set(groups)
    return user


def _load_player_institution_defaults() -> dict[str, str]:
    try:
        payload = json.loads(
            (settings.BASE_DIR / "university.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(
            f"Unable to load institution catalogue: {error}"
        ) from error

    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValidationError("Institution catalogue payload must contain a data list.")

    for record in records:
        if (
            not isinstance(record, dict)
            or str(record.get("value")) != HCMUS_INSTITUTION_VALUE
        ):
            continue
        label = record["label"].strip()
        return {
            "label": label,
            "normalized_label": normalize_institution_label(label),
            "code": record.get("code", "").strip(),
            "short_name": record.get("shortName", "").strip(),
            "english_name": record.get("eng", "").strip(),
            "type": record.get("type", "").strip(),
            "location": record.get("location", "").strip(),
            "review_status": Institution.ReviewStatus.VERIFIED,
        }

    raise ValidationError("HCMUS institution catalogue record is missing.")


def _seed_player_institution() -> Institution:
    institution, _ = Institution.objects.update_or_create(
        source=Institution.Source.CATALOGUE,
        value=HCMUS_INSTITUTION_VALUE,
        defaults=_load_player_institution_defaults(),
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
        student_id="",
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
        student_id="DEV-ORGANIZER-001",
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
        student_id="DEV-ADMIN-001",
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
    main_roster_size: int,
    substitute_limit: int,
    registration_opens_at: datetime,
    registration_closes_at: datetime,
    registration_capacity: int | None,
    fee_amount: Decimal,
) -> TournamentGame:
    tournament_game, _ = TournamentGame.objects.update_or_create(
        tournament=tournament,
        game=game,
        defaults={
            "main_roster_size": main_roster_size,
            "substitute_limit": substitute_limit,
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
        "arena-of-valor": _upsert_game(slug="arena-of-valor", name="Arena of Valor"),
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
    sponsor_open, _ = Tournament.objects.update_or_create(
        slug="dev-sponsor-open",
        defaults={
            "name": "USEC Publisher Showcase Open",
            "description": "Eight-team paid Valorant and League of Legends divisions.",
            "starts_at": now + timedelta(days=21),
            "ends_at": now + timedelta(days=22),
            "location": "HCMUS",
            "is_published": True,
        },
    )
    sponsor_arena, _ = Tournament.objects.update_or_create(
        slug="dev-sponsor-arena",
        defaults={
            "name": "USEC Arena of Valor Cup",
            "description": "Eight-team free Arena of Valor division.",
            "starts_at": now + timedelta(days=28),
            "ends_at": now + timedelta(days=29),
            "location": "HCMUS",
            "is_published": True,
        },
    )
    sponsor_expired, _ = Tournament.objects.update_or_create(
        slug="dev-sponsor-expired",
        defaults={
            "name": "USEC Publisher Showcase Archive",
            "description": "Eight-team divisions with expired registration windows.",
            "starts_at": now - timedelta(days=60),
            "ends_at": now - timedelta(days=59),
            "location": "HCMUS",
            "is_published": True,
        },
    )
    fpt_shop_uni_tour, _ = Tournament.objects.update_or_create(
        slug="dev-fpt-shop-uni-tour-2026",
        defaults={
            "name": "FPT Shop Uni Tour 2026 Development Fixture",
            "description": (
                "Synthetic 16-team Arena of Valor bracket modeled on the "
                "verified southern single-elimination structure."
            ),
            "starts_at": now + timedelta(days=21),
            "ends_at": now + timedelta(days=22),
            "location": "Development fixture",
            "is_published": True,
        },
    )

    double_elimination, _ = Tournament.objects.update_or_create(
        slug="dev-usec-double-elimination",
        defaults={
            "name": "USEC Synthetic Double Elimination",
            "description": "Synthetic teams and series allocation for bracket testing.",
            "students_only": False,
            "starts_at": now + timedelta(days=14),
            "ends_at": now + timedelta(days=15),
            "is_published": True,
        },
    )

    round_robin, _ = Tournament.objects.update_or_create(
        slug="dev-usec-round-robin",
        defaults={
            "name": "USEC Synthetic Round Robin",
            "description": "Fictional group schedules and qualification ties.",
            "students_only": False,
            "starts_at": now + timedelta(days=14),
            "ends_at": now + timedelta(days=15),
            "is_published": True,
        },
    )

    tournament_games = {
        "valorant": _upsert_tournament_game(
            tournament=current,
            game=games["valorant"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=16,
            fee_amount=Decimal("50000.00"),
        ),
        "chess": _upsert_tournament_game(
            tournament=current,
            game=games["chess"],
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=None,
            fee_amount=Decimal("0.00"),
        ),
        "counter-strike-2": _upsert_tournament_game(
            tournament=current,
            game=games["counter-strike-2"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=1,
            fee_amount=Decimal("75000.00"),
        ),
        "league-of-legends": _upsert_tournament_game(
            tournament=current,
            game=games["league-of-legends"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now + timedelta(days=2),
            registration_closes_at=now + timedelta(days=10),
            registration_capacity=8,
            fee_amount=Decimal("100000.00"),
        ),
        "rocket-league": _upsert_tournament_game(
            tournament=archive,
            game=games["rocket-league"],
            main_roster_size=3,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=75),
            registration_closes_at=now - timedelta(days=61),
            registration_capacity=8,
            fee_amount=Decimal("60000.00"),
        ),
        "ea-sports-fc": _upsert_tournament_game(
            tournament=draft,
            game=games["ea-sports-fc"],
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=14),
            registration_capacity=32,
            fee_amount=Decimal("30000.00"),
        ),
        "sponsor-valorant": _upsert_tournament_game(
            tournament=sponsor_open,
            game=games["valorant"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=14),
            registration_closes_at=now - timedelta(days=1),
            registration_capacity=8,
            fee_amount=Decimal("50000.00"),
        ),
        "sponsor-league-of-legends": _upsert_tournament_game(
            tournament=sponsor_open,
            game=games["league-of-legends"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=8,
            fee_amount=Decimal("100000.00"),
        ),
        "sponsor-arena-of-valor": _upsert_tournament_game(
            tournament=sponsor_arena,
            game=games["arena-of-valor"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=7),
            registration_closes_at=now + timedelta(days=7),
            registration_capacity=8,
            fee_amount=Decimal("0.00"),
        ),
        "sponsor-counter-strike-2": _upsert_tournament_game(
            tournament=sponsor_expired,
            game=games["counter-strike-2"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=90),
            registration_closes_at=now - timedelta(days=60),
            registration_capacity=8,
            fee_amount=Decimal("75000.00"),
        ),
        "sponsor-rocket-league": _upsert_tournament_game(
            tournament=sponsor_expired,
            game=games["rocket-league"],
            main_roster_size=3,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=90),
            registration_closes_at=now - timedelta(days=60),
            registration_capacity=8,
            fee_amount=Decimal("60000.00"),
        ),
        "fpt-lqm": _upsert_tournament_game(
            tournament=fpt_shop_uni_tour,
            game=games["arena-of-valor"],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=14),
            registration_closes_at=now - timedelta(days=1),
            registration_capacity=16,
            fee_amount=Decimal("0.00"),
        ),
    }
    for slug, size in (("valorant", 16), ("league-of-legends", 5)):
        tournament_games[f"double-{slug}"] = _upsert_tournament_game(
            tournament=double_elimination,
            game=games[slug],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=14),
            registration_closes_at=now - timedelta(days=1),
            registration_capacity=size,
            fee_amount=Decimal("0.00"),
        )
    for slug in ("valorant", "league-of-legends"):
        tournament_games[f"round-robin-{slug}"] = _upsert_tournament_game(
            tournament=round_robin,
            game=games[slug],
            main_roster_size=5,
            substitute_limit=0,
            registration_opens_at=now - timedelta(days=14),
            registration_closes_at=now - timedelta(days=1),
            registration_capacity=8,
            fee_amount=Decimal("0.00"),
        )
    return SeedCatalog(
        tournaments={
            current.slug: current,
            archive.slug: archive,
            draft.slug: draft,
            sponsor_open.slug: sponsor_open,
            sponsor_arena.slug: sponsor_arena,
            sponsor_expired.slug: sponsor_expired,
            fpt_shop_uni_tour.slug: fpt_shop_uni_tour,
            double_elimination.slug: double_elimination,
            round_robin.slug: round_robin,
        },
        tournament_games=tournament_games,
    )


def _member_inputs(
    roster: tuple[tuple[str, str], ...],
) -> tuple[RegistrationMemberInput, ...]:
    return tuple(
        RegistrationMemberInput(
            first_name_snapshot="Player",
            last_name_snapshot="Example",
            date_of_birth_snapshot=date(2005, 1, 1),
            student_id_snapshot="0012345",
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


def _upsert_development_team(
    *,
    now: datetime,
    organizer,
    division: TournamentGame,
    team_prefix: str,
    index: int,
) -> Registration:
    submitted_at = now - timedelta(days=3)
    team_tag = f"{team_prefix}{index:02d}"
    registration, _ = Registration.objects.update_or_create(
        tournament_game=division,
        contact_email_snapshot=(
            f"{division.tournament.slug}-{division.game.slug}-"
            f"team-{index}@example.invalid"
        ),
        defaults={
            "submitted_by": None,
            "submitter_role": Registration.SubmitterRole.CAPTAIN,
            "contact_facebook_snapshot": "https://facebook.com/example",
            "contact_phone_snapshot": f"090000{index:04d}",
            "team_name": f"{division.game.name} Team {index:02d}",
            "team_tag": team_tag,
            "status": Registration.Status.APPROVED,
            "fee_amount_snapshot": division.fee_amount,
            "fee_currency_snapshot": division.fee_currency,
            "payment_hold_minutes_snapshot": 60 if division.fee_amount > 0 else None,
            "payment_due_at": submitted_at + timedelta(minutes=60)
            if division.fee_amount > 0
            else None,
            "submitted_at": submitted_at,
        },
    )
    Registration.objects.filter(pk=registration.pk).update(
        created_at=submitted_at,
        submitted_at=submitted_at,
        updated_at=now,
    )
    RegistrationMember.objects.filter(
        registration=registration,
        display_order__gt=division.main_roster_size,
    ).delete()
    for member_number in range(1, division.main_roster_size + 1):
        RegistrationMember.objects.update_or_create(
            registration=registration,
            display_order=member_number,
            defaults={
                "user": None,
                "gamer_tag_snapshot": f"{team_tag}-P{member_number}",
                "first_name_snapshot": "Bracket",
                "last_name_snapshot": f"Player {index:02d}-{member_number}",
                "date_of_birth_snapshot": date(2005, member_number, 1),
                "school_snapshot": "HCMUS",
                "is_captain": member_number == 1,
                "roster_role": RegistrationMember.RosterRole.MAIN,
            },
        )

    RegistrationStatusEvent.objects.filter(registration=registration).delete()
    RegistrationStatusEvent.objects.create(
        registration=registration,
        from_status="",
        to_status=Registration.Status.SUBMITTED,
        note="Development team fixture.",
        created_at=submitted_at,
    )
    RegistrationStatusEvent.objects.create(
        registration=registration,
        from_status=Registration.Status.SUBMITTED,
        to_status=Registration.Status.APPROVED,
        actor=organizer,
        note="Development team fixture approved.",
        created_at=submitted_at + timedelta(hours=1),
    )

    if division.fee_amount > 0:
        PaymentIntent.objects.update_or_create(
            registration=registration,
            defaults={
                "tournament_game": division,
                "reference": f"DEV-{team_prefix}{index:02d}",
                "amount": division.fee_amount,
                "currency": division.fee_currency,
                "bank_name_snapshot": "DEVELOPMENT SAMPLE",
                "account_holder_snapshot": "DEVELOPMENT SAMPLE DO NOT PAY",
            },
        )
        attempt = registration.payment_attempts.order_by("pk").first()
        if attempt is None:
            attempt = PaymentAttempt(
                registration=registration,
                method=PaymentAttempt.Method.MANUAL_PROOF,
            )
            attempt.proof_file = _sample_payment_image()
        attempt.status = PaymentAttempt.Status.VERIFIED
        attempt.amount = division.fee_amount
        attempt.currency = division.fee_currency
        attempt.reference = f"DEV-{team_prefix}{index:02d}"
        attempt.reviewed_by = organizer
        attempt.reviewed_at = submitted_at + timedelta(hours=2)
        attempt.review_note = "Development sponsor fixture payment verified."
        attempt.save()
        PaymentAttempt.objects.filter(registration=registration).exclude(
            pk=attempt.pk
        ).delete()
        PaymentAttempt.objects.filter(pk=attempt.pk).update(
            created_at=submitted_at + timedelta(hours=1)
        )
    else:
        PaymentIntent.objects.filter(registration=registration).delete()
        PaymentAttempt.objects.filter(registration=registration).delete()

    return registration


def _seed_sponsor_teams(
    *, now: datetime, organizer, catalog: SeedCatalog
) -> dict[str, tuple[Registration, ...]]:
    divisions = (
        ("sponsor-valorant", "VAL"),
        ("sponsor-league-of-legends", "LOL"),
        ("sponsor-arena-of-valor", "AOV"),
        ("sponsor-counter-strike-2", "CS2"),
        ("sponsor-rocket-league", "RLG"),
    )
    return {
        key: tuple(
            _upsert_development_team(
                now=now,
                organizer=organizer,
                division=catalog.tournament_games[key],
                team_prefix=prefix,
                index=index,
            )
            for index in range(1, 9)
        )
        for key, prefix in divisions
    }


def _rebuild_registrations(
    *,
    now: datetime,
    player,
    organizer,
    catalog: SeedCatalog,
) -> tuple[Registration, ...]:
    previous_registrations = Registration.objects.filter(
        submitted_by=player,
        tournament_game__tournament__slug__in=SEED_TOURNAMENT_SLUGS,
    )
    previous_proofs = [
        attempt.proof_file
        for attempt in PaymentAttempt.objects.filter(
            registration__in=previous_registrations
        )
        if attempt.proof_file
    ]
    PaymentIntent.objects.filter(registration__in=previous_registrations).delete()
    previous_registrations.delete()

    def remove_replaced_proofs():
        for proof in previous_proofs:
            if not PaymentAttempt.objects.filter(proof_file=proof.name).exists():
                proof.storage.delete(proof.name)

    transaction.on_commit(remove_replaced_proofs)

    valorant = submit_registration(
        submitter_role="captain",
        contact_facebook_snapshot="https://facebook.com/example",
        contact_phone_snapshot="0900000000",
        submitted_by=player,
        tournament_game_id=catalog.tournament_games["valorant"].pk,
        team_name="Blue Phoenix",
        team_tag="BP",
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
        proof_file=_sample_payment_image(),
        actor=player,
        registration_id=valorant.pk,
        amount=Decimal("50000.00"),
        currency="VND",
        reference="DEV-VAL-PENDING",
    )

    chess = submit_registration(
        submitter_role="captain",
        contact_facebook_snapshot="https://facebook.com/example",
        contact_phone_snapshot="0900000000",
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
        submitter_role="captain",
        contact_facebook_snapshot="https://facebook.com/example",
        contact_phone_snapshot="0900000000",
        submitted_by=player,
        tournament_game_id=catalog.tournament_games["counter-strike-2"].pk,
        team_name="Campus Five",
        team_tag="C5",
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
        proof_file=_sample_payment_image(),
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
        submitter_role="captain",
        contact_facebook_snapshot="https://facebook.com/example",
        contact_phone_snapshot="0900000000",
        submitted_by=player,
        tournament_game_id=rocket_game.pk,
        team_name="Orbit Three",
        team_tag="O3",
        members=_member_inputs(
            (
                ("Rookie", "HCMUS"),
                ("Comet", "HCMUT"),
                ("Vector", "UIT"),
            )
        ),
    )
    rejected_payment = submit_payment_attempt(
        proof_file=_sample_payment_image(),
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
        proof_file=_sample_payment_image(),
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


def _publish_single_elimination_bracket(
    *,
    now: datetime,
    organizer,
    division: TournamentGame,
    registrations: tuple[Registration, ...],
    name: str,
    default_series_length: int = 3,
    round_series_lengths: dict[int, int] | None = None,
) -> None:
    existing = Competition.objects.filter(tournament_game=division).first()
    if existing:
        if existing.stages.filter(draws__state=StageDraw.State.PUBLISHED).exists():
            return
        raise ValidationError(
            f"The development {division.game.name} competition is incomplete."
        )

    competition = create_competition(actor=organizer, tournament_game_id=division.pk)
    configure_elimination(
        format="SINGLE_ELIMINATION",
        actor=organizer,
        competition_id=competition.pk,
        expected_revision=competition.revision,
        name=name,
        default_series_length=default_series_length,
    )
    competition.refresh_from_db()
    entrants = select_entrants(
        actor=organizer,
        competition_id=competition.pk,
        expected_revision=competition.revision,
        registration_ids=[registration.pk for registration in registrations],
    )
    competition.refresh_from_db()
    draw = save_elimination_draw(
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
    for round_ in draw.rounds.order_by("number"):
        series_length = (round_series_lengths or {}).get(round_.number)
        if series_length is not None:
            competition.refresh_from_db()
            set_round_series_length(
                actor=organizer,
                round_id=round_.pk,
                expected_revision=competition.revision,
                series_length=series_length,
            )
    competition.refresh_from_db()
    first_match = (
        Match.objects.filter(round__draw=draw, status=Match.Status.PENDING)
        .order_by("round__number", "number")
        .first()
    )
    if first_match:
        schedule_match(
            actor=organizer,
            match_id=first_match.pk,
            expected_revision=competition.revision,
            scheduled_at=now + timedelta(days=14, hours=2),
        )


def _seed_published_bracket(*, now: datetime, organizer, catalog: SeedCatalog) -> None:
    division = catalog.tournament_games["chess"]
    existing = Competition.objects.filter(tournament_game=division).first()
    if existing:
        if existing.stages.filter(draws__state=StageDraw.State.PUBLISHED).exists():
            return
        raise ValidationError("The development chess competition is incomplete.")

    registrations = []
    for index, gamer_tag in enumerate(
        ("Knight", "Bishop", "Rook", "Queen", "King"), start=1
    ):
        registration, _ = Registration.objects.update_or_create(
            tournament_game=division,
            contact_email_snapshot=f"bracket-{index}@example.invalid",
            defaults={
                "submitter_role": Registration.SubmitterRole.CAPTAIN,
                "contact_facebook_snapshot": "https://facebook.com/example",
                "contact_phone_snapshot": f"09000000{index:02d}",
                "status": Registration.Status.APPROVED,
                "fee_amount_snapshot": Decimal("0.00"),
                "fee_currency_snapshot": "VND",
                "submitted_at": now - timedelta(days=7 - index),
            },
        )
        RegistrationMember.objects.update_or_create(
            registration=registration,
            display_order=1,
            defaults={
                "gamer_tag_snapshot": gamer_tag,
                "first_name_snapshot": "Bracket",
                "last_name_snapshot": f"Player {index}",
                "date_of_birth_snapshot": date(2005, 1, index),
                "school_snapshot": "HCMUS",
                "is_captain": True,
            },
        )
        registrations.append(registration)

    _publish_single_elimination_bracket(
        now=now,
        organizer=organizer,
        division=division,
        registrations=tuple(registrations),
        name="Development final bracket",
    )


def _seed_sponsor_bracket(
    *,
    now: datetime,
    organizer,
    catalog: SeedCatalog,
    sponsor_teams: dict[str, tuple[Registration, ...]],
) -> None:
    _publish_single_elimination_bracket(
        now=now,
        organizer=organizer,
        division=catalog.tournament_games["sponsor-league-of-legends"],
        registrations=sponsor_teams["sponsor-league-of-legends"],
        name="Publisher showcase League of Legends bracket",
    )


def _seed_fpt_shop_uni_tour_bracket(
    *, now: datetime, organizer, catalog: SeedCatalog
) -> None:
    division = catalog.tournament_games["fpt-lqm"]
    registrations = tuple(
        _upsert_development_team(
            now=now,
            organizer=organizer,
            division=division,
            team_prefix="FPT",
            index=index,
        )
        for index in range(1, 17)
    )
    _publish_single_elimination_bracket(
        now=now,
        organizer=organizer,
        division=division,
        registrations=registrations,
        name="Synthetic FPT Shop Uni Tour 2026 LQM bracket",
        default_series_length=1,
        round_series_lengths={3: 3, 4: 3},
    )


def _seed_double_elimination(*, now: datetime, organizer, catalog: SeedCatalog) -> None:
    for slug, size, policy in (
        ("valorant", 16, Stage.GrandFinalPolicy.RESET),
        ("league-of-legends", 5, Stage.GrandFinalPolicy.NO_RESET),
    ):
        division = catalog.tournament_games[f"double-{slug}"]
        registrations = [
            _upsert_development_team(
                now=now,
                organizer=organizer,
                division=division,
                team_prefix="DE",
                index=index,
            )
            for index in range(1, size + 1)
        ]
        existing = Competition.objects.filter(tournament_game=division).first()
        if existing:
            if existing.stages.filter(draws__state=StageDraw.State.PUBLISHED).exists():
                continue
            raise ValidationError(
                "The development double-elimination competition is incomplete."
            )
        competition = create_competition(
            actor=organizer, tournament_game_id=division.pk
        )
        configure_elimination(
            actor=organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            name=f"Synthetic {size}-team {policy.lower().replace('_', '-')} bracket",
            format=Stage.Format.DOUBLE_ELIMINATION,
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
        draw = save_elimination_draw(
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
        if policy == Stage.GrandFinalPolicy.RESET:
            # Synthetic allocation: BO1 early rounds, BO3 late rounds and finals.
            for round_ in draw.rounds.all():
                if (
                    round_.section == Round.Section.UPPER
                    and round_.number >= 3
                    or round_.section == Round.Section.LOWER
                    and round_.number == 6
                    or round_.section == Round.Section.FINALS
                ):
                    competition.refresh_from_db()
                    set_round_series_length(
                        actor=organizer,
                        round_id=round_.pk,
                        expected_revision=competition.revision,
                        series_length=3,
                    )
        else:
            while Match.objects.filter(
                round__draw=draw, status=Match.Status.PENDING
            ).exists():
                ready = next(
                    (
                        match
                        for match in Match.objects.filter(
                            round__draw=draw, status=Match.Status.PENDING
                        )
                        .prefetch_related("slots")
                        .order_by("pk")
                        if all(
                            slot.is_resolved and slot.resolved_entry_id
                            for slot in match.slots.all()
                        )
                    ),
                    None,
                )
                if ready is None:
                    raise ValidationError(
                        "The development no-reset bracket cannot advance."
                    )
                competition.refresh_from_db()
                finalize_match(
                    actor=organizer,
                    match_id=ready.pk,
                    expected_revision=competition.revision,
                    outcome=Match.Outcome.PLAYED,
                    side_one_score=1,
                    side_two_score=0,
                )


def _seed_round_robin(*, now: datetime, organizer, catalog: SeedCatalog) -> None:
    for slug, meetings, mode, length in (
        ("valorant", 1, "FIXED_GAMES", 2),
        ("league-of-legends", 2, "BEST_OF", 3),
    ):
        division = catalog.tournament_games[f"round-robin-{slug}"]
        registrations = [
            _upsert_development_team(
                now=now,
                organizer=organizer,
                division=division,
                team_prefix="RR",
                index=index,
            )
            for index in range(1, 9)
        ]
        existing = Competition.objects.filter(tournament_game=division).first()
        if existing:
            if existing.stages.filter(draws__state="PUBLISHED").exists():
                continue
            raise ValidationError(
                "The development round robin competition is incomplete."
            )
        competition = create_competition(
            actor=organizer, tournament_game_id=division.pk
        )
        configure_round_robin(
            actor=organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            name="Synthetic groups",
            meetings=meetings,
            series_mode=mode,
            default_series_length=length,
            win_points=3,
            draw_points=1,
            loss_points=0,
            tiebreaks=[]
            if meetings == 1
            else ["HEAD_TO_HEAD", "GAME_DIFFERENCE", "GAMES_WON"],
        )
        competition.refresh_from_db()
        entrants = select_entrants(
            actor=organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            registration_ids=[r.pk for r in registrations],
        )
        ids = [e.pk for e in entrants]
        split = 3 if meetings == 1 else 4
        competition.refresh_from_db()
        draw = save_round_robin_draw(
            actor=organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            group_specs=[("Alpha", 1), ("Beta", 2)],
            ordered_entrant_ids=ids,
            memberships=[ids[:split], ids[split:]],
        )
        competition.refresh_from_db()
        publish_draw(
            actor=organizer,
            competition_id=competition.pk,
            expected_revision=competition.revision,
        )
        alpha, beta = list(draw.groups.all())
        for group in (alpha, beta) if meetings == 1 else (alpha,):
            for match in Match.objects.filter(round__group=group).prefetch_related(
                "slots__resolved_entry"
            ):
                slots = list(match.slots.all())
                first_wins = slots[0].resolved_entry.seed < slots[1].resolved_entry.seed
                competition.refresh_from_db()
                finalize_match(
                    actor=organizer,
                    match_id=match.pk,
                    expected_revision=competition.revision,
                    outcome="PLAYED",
                    side_one_score=1 if meetings == 1 else 2 * first_wins,
                    side_two_score=1 if meetings == 1 else 2 * (not first_wins),
                )
        if meetings == 1:
            competition.refresh_from_db()
            tie = group_standings(alpha)["cutoff_ties"][0]
            preview = preview_group_tie(
                actor=organizer,
                group_id=alpha.pk,
                expected_revision=competition.revision,
                tied_entry_ids=tie["entry_ids"],
                method="EXTRA_MATCHES",
            )
            resolution = confirm_group_tie(actor=organizer, token=preview["token"])
            extra = Match.objects.filter(round__tie_resolution=resolution).first()
            competition.refresh_from_db()
            finalize_match(
                actor=organizer,
                match_id=extra.pk,
                expected_revision=competition.revision,
                outcome="PLAYED",
                side_one_score=1,
                side_two_score=0,
            )
            target = Match.objects.filter(
                round__group=alpha, round__section="NORMAL"
            ).first()
            for one, two in ((2, 0), (1, 1)):
                competition.refresh_from_db()
                preview = preview_correction(
                    actor=organizer,
                    match_id=target.pk,
                    expected_revision=competition.revision,
                    outcome="PLAYED",
                    side_one_score=one,
                    side_two_score=two,
                )
                apply_correction(
                    actor=organizer,
                    token=preview["token"],
                    internal_reason="Synthetic score-correction example.",
                )
            competition.refresh_from_db()
            preview = preview_group_tie(
                actor=organizer,
                group_id=alpha.pk,
                expected_revision=competition.revision,
                tied_entry_ids=tie["entry_ids"],
                method="MANUAL",
                ordered_entry_ids=list(reversed(tie["entry_ids"])),
            )
            confirm_group_tie(
                actor=organizer,
                token=preview["token"],
                internal_reason="Fictional organizer-decision example.",
            )
            competition.refresh_from_db()
            tie = group_standings(beta)["cutoff_ties"][0]
            preview = preview_group_tie(
                actor=organizer,
                group_id=beta.pk,
                expected_revision=competition.revision,
                tied_entry_ids=tie["entry_ids"],
                method="EXTRA_MATCHES",
                series_length=3,
            )
            resolution = confirm_group_tie(actor=organizer, token=preview["token"])
            live = Match.objects.filter(round__tie_resolution=resolution).first()
        else:
            live = Match.objects.filter(round__group=beta).first()
            competition.refresh_from_db()
            set_round_series_length(
                actor=organizer,
                round_id=live.round_id,
                expected_revision=competition.revision,
                series_length=5,
            )
        competition.refresh_from_db()
        schedule_match(
            actor=organizer,
            match_id=live.pk,
            expected_revision=competition.revision,
            scheduled_at=now + timedelta(hours=2),
        )
        competition.refresh_from_db()
        save_match_progress(
            actor=organizer,
            match_id=live.pk,
            expected_revision=competition.revision,
            side_one_score=1,
            side_two_score=0,
        )


@contextmanager
def _development_payment_destination():
    """Use fictional snapshots only for this command's fixtures, never public settings.

    The outer transaction and row lock keep temporary configuration invisible and
    preserve concurrent operator edits. Errors roll back the entire fixture build.
    """
    with transaction.atomic():
        destination, created = (
            PaymentSettings.objects.select_for_update().get_or_create(pk=1)
        )
        original = {
            field.attname: getattr(destination, field.attname)
            for field in PaymentSettings._meta.concrete_fields
            if not field.primary_key
        }
        PaymentSettings.objects.filter(pk=destination.pk).update(
            enabled=True,
            bank_name="DEVELOPMENT SAMPLE - NOT A RECEIVING BANK",
            bank_bin="970436",
            account_number="000000000000",
            account_holder="DEVELOPMENT SAMPLE DO NOT PAY",
            payment_hold_minutes=60,
        )
        yield
        if created:
            destination.delete()
        else:
            PaymentSettings.objects.filter(pk=destination.pk).update(**original)


def seed_development_data(*, now: datetime) -> DevelopmentSeedResult:
    player, organizer, admin = _seed_accounts()
    catalog = _seed_catalog(now=now)
    with _development_payment_destination():
        registrations = _rebuild_registrations(
            now=now,
            player=player,
            organizer=organizer,
            catalog=catalog,
        )
    _seed_published_bracket(now=now, organizer=organizer, catalog=catalog)
    sponsor_teams = _seed_sponsor_teams(
        now=now,
        organizer=organizer,
        catalog=catalog,
    )
    _seed_sponsor_bracket(
        now=now,
        organizer=organizer,
        catalog=catalog,
        sponsor_teams=sponsor_teams,
    )
    _seed_fpt_shop_uni_tour_bracket(
        now=now,
        organizer=organizer,
        catalog=catalog,
    )
    _seed_double_elimination(now=now, organizer=organizer, catalog=catalog)
    _seed_round_robin(now=now, organizer=organizer, catalog=catalog)
    return DevelopmentSeedResult(
        account_emails=(player.email, organizer.email, admin.email),
        tournament_slugs=tuple(catalog.tournaments),
        registration_ids=tuple(registration.pk for registration in registrations),
    )
