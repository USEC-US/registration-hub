# Development Seed Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, idempotent Django management command that creates documented local accounts and a representative matrix of tournament, registration, and payment scenarios for manual testing.

**Architecture:** Keep the management command thin: it owns the `DEBUG` safety gate, one outer database transaction, conversion of expected failures to `CommandError`, and human-readable output. Put deterministic account, catalog, registration, payment, transition, and timestamp orchestration in a focused `registrations.dev_seed` module so the command remains easy to audit and the seed workflow can be tested through the public command interface.

**Tech Stack:** Python 3.12+, Django 6.0.7+, Django REST Framework 3.17.1+, PostgreSQL, Django `TestCase`, existing registration domain services, Ruff.

## Global Constraints

- The command name is exactly `seed_dev_data`.
- The normal invocation is `uv run python manage.py seed_dev_data` from `server/`.
- Predictable seed credentials must never be created automatically by migrations, deployment, or server startup.
- Refuse execution when `DEBUG=False` unless `--allow-non-debug` is explicitly supplied.
- Run the complete bootstrap and seed operation inside one `transaction.atomic()` boundary.
- Capture `timezone.now()` once in the command and pass it into seed orchestration.
- Reuse `bootstrap_organizers` and the existing registration/payment/review domain services.
- Use reference-only payment attempts; do not create media files.
- Reruns may restore command-owned accounts, `dev-usec-*` tournaments, and the seeded player's registrations in those tournaments.
- Do not flush or modify unrelated local records.
- Add no new dependency, model field, migration, fixture format, or frontend source change.
- Do not stage or modify the existing unrelated `.superpowers/sdd/progress.md`, `docs/2026-07-14-spec.md`, or `docs/2026-07-15-conversation.md` working-tree changes.

---

## File Structure

- Create `server/registrations/dev_seed.py`: constants, result types, account reconciliation, catalog reconciliation, canonical registration/payment scenarios, and relative timestamp restoration.
- Create `server/registrations/management/commands/seed_dev_data.py`: argument parsing, development safety check, transaction boundary, organizer bootstrap, error conversion, and terminal summary.
- Create `server/registrations/tests/test_seed_dev_data_command.py`: command-level safety, account, permission, API visibility, availability, status, payment, idempotency, preservation, and rollback tests.
- Modify `server/README.md`: usage, safety warning, credentials, scenario map, and rerun ownership rules.

No migration or frontend file is part of this plan.

---

### Task 1: Safe Command Shell and Seed Accounts

**Files:**

- Create: `server/registrations/dev_seed.py`
- Create: `server/registrations/management/commands/seed_dev_data.py`
- Create: `server/registrations/tests/test_seed_dev_data_command.py`

**Interfaces:**

- Consumes: existing `bootstrap_organizers` management command and Django's configured `AUTH_USER_MODEL`.
- Produces: `seed_development_data(*, now: datetime) -> DevelopmentSeedResult`, account constants, and the `seed_dev_data` command with `--allow-non-debug`.

- [ ] **Step 1: Write failing command safety and account tests**

Create `server/registrations/tests/test_seed_dev_data_command.py` with:

```python
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


@override_settings(DEBUG=True)
class SeedDevDataCommandTests(TestCase):
    def run_seed(self, **options) -> str:
        output = StringIO()
        call_command("seed_dev_data", stdout=output, **options)
        return output.getvalue()

    @override_settings(DEBUG=False)
    def test_command_requires_explicit_non_debug_override(self):
        with self.assertRaisesMessage(
            CommandError,
            "seed_dev_data creates predictable credentials",
        ):
            self.run_seed()

        self.assertFalse(
            get_user_model().objects.filter(email="player@email.com").exists()
        )

        self.run_seed(allow_non_debug=True)

        self.assertTrue(
            get_user_model().objects.filter(email="player@email.com").exists()
        )

    def test_command_creates_documented_accounts_and_permissions(self):
        output = self.run_seed()
        user_model = get_user_model()

        player = user_model.objects.get(email="player@email.com")
        organizer = user_model.objects.get(email="organizer@email.com")
        admin = user_model.objects.get(email="admin@email.com")

        self.assertTrue(player.check_password("player@123"))
        self.assertEqual(player.gamer_tag, "Rookie")
        self.assertEqual(player.school, "HCMUS")
        self.assertTrue(player.is_active)
        self.assertFalse(player.is_staff)
        self.assertFalse(player.is_superuser)
        self.assertFalse(player.groups.exists())

        self.assertTrue(organizer.check_password("organizer@123"))
        self.assertTrue(organizer.is_active)
        self.assertTrue(organizer.is_staff)
        self.assertFalse(organizer.is_superuser)
        self.assertSetEqual(
            set(organizer.groups.values_list("name", flat=True)),
            {"Organizers"},
        )
        self.assertTrue(organizer.has_perm("registrations.change_registration"))
        self.assertTrue(organizer.has_perm("registrations.change_paymentattempt"))
        self.assertFalse(organizer.has_perm("registrations.delete_registration"))

        self.assertTrue(admin.check_password("admin@123"))
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertFalse(admin.groups.exists())

        self.assertEqual(Group.objects.filter(name="Organizers").count(), 1)
        self.assertIn("Player: player@email.com / player@123", output)
        self.assertIn("Organizer: organizer@email.com / organizer@123", output)
        self.assertIn("Admin: admin@email.com / admin@123", output)
```

- [ ] **Step 2: Run the focused tests and confirm the command is missing**

Run from `server/`:

```powershell
uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2
```

Expected: both tests error with `Unknown command: 'seed_dev_data'`.

- [ ] **Step 3: Implement account reconciliation in the seed module**

Create `server/registrations/dev_seed.py` with:

```python
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
```

- [ ] **Step 4: Implement the command safety gate, transaction, bootstrap, and output**

Create `server/registrations/management/commands/seed_dev_data.py` with:

```python
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
```

- [ ] **Step 5: Run the focused tests and confirm account behavior passes**

Run:

```powershell
uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2
```

Expected: `Ran 2 tests` and `OK`.

- [ ] **Step 6: Run Ruff on the new files**

Run:

```powershell
uv run ruff check registrations/dev_seed.py registrations/management/commands/seed_dev_data.py registrations/tests/test_seed_dev_data_command.py
```

Expected: `All checks passed!`.

- [ ] **Step 7: Commit the safe command shell**

```powershell
git add server/registrations/dev_seed.py server/registrations/management/commands/seed_dev_data.py server/registrations/tests/test_seed_dev_data_command.py
git commit -m "feat: add safe development seed command" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Tournament Catalog and Public Availability Scenarios

**Files:**

- Modify: `server/registrations/dev_seed.py`
- Modify: `server/registrations/tests/test_seed_dev_data_command.py`

**Interfaces:**

- Consumes: `seed_development_data(*, now)` and `DevelopmentSeedResult` from Task 1.
- Produces: `_seed_catalog(*, now: datetime) -> SeedCatalog`, stable game/tournament records, and public `open`, `not_open`, and `closed` states. Counter-Strike 2 becomes `full` after Task 3 creates its active registration.

- [ ] **Step 1: Add a failing public catalog test**

Extend the imports in `server/registrations/tests/test_seed_dev_data_command.py` with:

```python
from rest_framework.test import APIClient

from tournaments.models import Tournament
```

Add this method to `SeedDevDataCommandTests`:

```python
    def test_command_seeds_public_availability_and_hides_draft(self):
        self.run_seed()
        client = APIClient()

        list_response = client.get("/api/tournaments/")
        self.assertEqual(list_response.status_code, 200)
        self.assertSetEqual(
            {item["slug"] for item in list_response.data},
            {"dev-usec-current", "dev-usec-archive"},
        )

        current_response = client.get("/api/tournaments/dev-usec-current/")
        self.assertEqual(current_response.status_code, 200)
        current_states = {
            game["game_slug"]: game["registration_state"]
            for game in current_response.data["tournament_games"]
        }
        self.assertEqual(
            current_states,
            {
                "valorant": "open",
                "chess": "open",
                "counter-strike-2": "open",
                "league-of-legends": "not_open",
            },
        )

        archive_response = client.get("/api/tournaments/dev-usec-archive/")
        self.assertEqual(archive_response.status_code, 200)
        self.assertEqual(
            archive_response.data["tournament_games"][0]["registration_state"],
            "closed",
        )

        draft_response = client.get("/api/tournaments/dev-usec-draft/")
        self.assertEqual(draft_response.status_code, 404)
        self.assertFalse(
            Tournament.objects.get(slug="dev-usec-draft").is_published
        )
```

- [ ] **Step 2: Run the new test and confirm the catalog is absent**

Run:

```powershell
uv run python manage.py test registrations.tests.test_seed_dev_data_command.SeedDevDataCommandTests.test_command_seeds_public_availability_and_hides_draft -v 2
```

Expected: FAIL because the public tournament list is empty.

- [ ] **Step 3: Add catalog types, imports, and reconciliation helpers**

Replace the import block at the top of `server/registrations/dev_seed.py` with:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from tournaments.models import Game, Tournament, TournamentGame
```

Add this type after `DevelopmentSeedResult`:

```python
@dataclass(frozen=True)
class SeedCatalog:
    tournaments: dict[str, Tournament]
    tournament_games: dict[str, TournamentGame]
```

Add these helpers before `seed_development_data`:

```python
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
```

Replace `seed_development_data` with:

```python
def seed_development_data(*, now: datetime) -> DevelopmentSeedResult:
    accounts = _seed_accounts()
    catalog = _seed_catalog(now=now)
    return DevelopmentSeedResult(
        account_emails=tuple(account.email for account in accounts),
        tournament_slugs=tuple(catalog.tournaments),
        registration_ids=(),
    )
```

- [ ] **Step 4: Run catalog and account tests**

Run:

```powershell
uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2
```

Expected: `Ran 3 tests` and `OK`.

- [ ] **Step 5: Run Ruff on the changed module and test**

Run:

```powershell
uv run ruff check registrations/dev_seed.py registrations/tests/test_seed_dev_data_command.py
```

Expected: `All checks passed!`.

- [ ] **Step 6: Commit the catalog scenarios**

```powershell
git add server/registrations/dev_seed.py server/registrations/tests/test_seed_dev_data_command.py
git commit -m "feat: seed tournament availability scenarios" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Registration, Payment, Timeline, Idempotency, and Rollback Scenarios

**Files:**

- Modify: `server/registrations/dev_seed.py`
- Modify: `server/registrations/management/commands/seed_dev_data.py`
- Modify: `server/registrations/tests/test_seed_dev_data_command.py`

**Interfaces:**

- Consumes: `SeedCatalog`, the seeded player and organizer accounts, and existing service signatures `submit_registration`, `submit_payment_attempt`, `review_payment_attempt`, `start_review`, `approve_registration`, and `reject_registration`.
- Produces: four canonical participant registrations, four payment attempts, nine status events, coherent relative timestamps, full-state capacity, deterministic scenario output, and transactional restoration on rerun.

- [ ] **Step 1: Add failing registration and payment matrix assertions**

Extend imports in `server/registrations/tests/test_seed_dev_data_command.py` with:

```python
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.utils import timezone

from registrations.models import PaymentAttempt, Registration, RegistrationStatusEvent
from tournaments.models import Game, Tournament, TournamentGame
```

Replace the expected `counter-strike-2` state in `test_command_seeds_public_availability_and_hides_draft`:

```python
                "counter-strike-2": "full",
```

Add these methods to `SeedDevDataCommandTests`:

```python
    def test_command_seeds_registration_status_payment_and_timeline_matrix(self):
        output = self.run_seed()
        player = get_user_model().objects.get(email="player@email.com")
        registrations = {
            registration.tournament_game.game.slug: registration
            for registration in Registration.objects.filter(submitted_by=player)
            .select_related("tournament_game__game", "tournament_game__tournament")
            .prefetch_related("payment_attempts", "status_events")
        }

        self.assertSetEqual(
            set(registrations),
            {"valorant", "chess", "counter-strike-2", "rocket-league"},
        )
        self.assertIn("Valorant: SUBMITTED / payment PENDING", output)
        self.assertIn("Development draft: unpublished", output)
        self.assertEqual(
            registrations["valorant"].status,
            Registration.Status.SUBMITTED,
        )
        self.assertEqual(
            registrations["chess"].status,
            Registration.Status.APPROVED,
        )
        self.assertEqual(
            registrations["counter-strike-2"].status,
            Registration.Status.UNDER_REVIEW,
        )
        self.assertEqual(
            registrations["rocket-league"].status,
            Registration.Status.REJECTED,
        )

        payment_statuses = {
            slug: list(
                registration.payment_attempts.order_by("created_at", "pk").values_list(
                    "status", flat=True
                )
            )
            for slug, registration in registrations.items()
        }
        self.assertEqual(payment_statuses["valorant"], [PaymentAttempt.Status.PENDING])
        self.assertEqual(payment_statuses["chess"], [])
        self.assertEqual(
            payment_statuses["counter-strike-2"],
            [PaymentAttempt.Status.VERIFIED],
        )
        self.assertEqual(
            payment_statuses["rocket-league"],
            [PaymentAttempt.Status.REJECTED, PaymentAttempt.Status.PENDING],
        )
        self.assertFalse(
            any(
                attempt.proof_file.name
                for attempt in PaymentAttempt.objects.filter(
                    registration__submitted_by=player
                )
            )
        )

        event_statuses = {
            slug: list(
                registration.status_events.values_list("to_status", flat=True)
            )
            for slug, registration in registrations.items()
        }
        self.assertEqual(event_statuses["valorant"], [Registration.Status.SUBMITTED])
        self.assertEqual(
            event_statuses["chess"],
            [
                Registration.Status.SUBMITTED,
                Registration.Status.UNDER_REVIEW,
                Registration.Status.APPROVED,
            ],
        )
        self.assertEqual(
            event_statuses["counter-strike-2"],
            [Registration.Status.SUBMITTED, Registration.Status.UNDER_REVIEW],
        )
        self.assertEqual(
            event_statuses["rocket-league"],
            [
                Registration.Status.SUBMITTED,
                Registration.Status.UNDER_REVIEW,
                Registration.Status.REJECTED,
            ],
        )
        self.assertEqual(
            registrations["rocket-league"].status_events.last().note,
            "Eligibility documents were incomplete.",
        )
        self.assertLess(
            registrations["rocket-league"].submitted_at,
            registrations["rocket-league"].tournament_game.tournament.starts_at,
        )
        self.assertEqual(
            list(registrations["rocket-league"].status_events.values_list("created_at", flat=True)),
            sorted(
                registrations["rocket-league"].status_events.values_list(
                    "created_at", flat=True
                )
            ),
        )

    def test_rerun_restores_seed_owned_data_and_preserves_unrelated_records(self):
        self.run_seed()
        user_model = get_user_model()
        player = user_model.objects.get(email="player@email.com")
        organizers = Group.objects.get(name="Organizers")
        player.gamer_tag = "Changed"
        player.school = "Changed"
        player.is_staff = True
        player.is_superuser = True
        player.set_unusable_password()
        player.save()
        player.groups.add(organizers)

        current = Tournament.objects.get(slug="dev-usec-current")
        current.name = "Changed"
        current.save(update_fields=("name",))
        Registration.objects.filter(
            submitted_by=player,
            tournament_game__game__slug="valorant",
        ).update(team_name="Changed")
        TournamentGame.objects.filter(
            tournament__slug="dev-usec-current",
            game__slug="valorant",
        ).update(fee_amount=Decimal("1.00"))
        PaymentAttempt.objects.filter(
            registration__submitted_by=player,
            registration__tournament_game__game__slug="valorant",
        ).update(
            status=PaymentAttempt.Status.VERIFIED,
            reference="Changed",
        )

        outsider = user_model.objects.create_user(
            email="outsider@example.com",
            password="strong-password",
        )
        outsider_game = Game.objects.create(name="Unrelated Game", slug="unrelated-game")
        outsider_tournament = Tournament.objects.create(
            name="Unrelated Tournament",
            slug="unrelated-tournament",
            is_published=True,
        )
        outsider_tournament_game = TournamentGame.objects.create(
            tournament=outsider_tournament,
            game=outsider_game,
            team_size_min=1,
            team_size_max=1,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            registration_capacity=None,
            fee_amount=Decimal("0.00"),
            fee_currency="VND",
        )
        outsider_registration = Registration.objects.create(
            tournament_game=outsider_tournament_game,
            submitted_by=outsider,
            team_name="",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=Decimal("0.00"),
            fee_currency_snapshot="VND",
        )

        self.run_seed()

        player.refresh_from_db()
        self.assertTrue(player.check_password("player@123"))
        self.assertEqual(player.gamer_tag, "Rookie")
        self.assertEqual(player.school, "HCMUS")
        self.assertFalse(player.is_staff)
        self.assertFalse(player.is_superuser)
        self.assertFalse(player.groups.exists())
        self.assertEqual(
            Tournament.objects.get(slug="dev-usec-current").name,
            "USEC Development Open",
        )

        seeded_registrations = Registration.objects.filter(
            submitted_by=player,
            tournament_game__tournament__slug__in=(
                "dev-usec-current",
                "dev-usec-archive",
                "dev-usec-draft",
            ),
        )
        self.assertEqual(seeded_registrations.count(), 4)
        self.assertEqual(
            PaymentAttempt.objects.filter(
                registration__in=seeded_registrations
            ).count(),
            4,
        )
        self.assertEqual(
            RegistrationStatusEvent.objects.filter(
                registration__in=seeded_registrations
            ).count(),
            9,
        )
        self.assertEqual(
            seeded_registrations.get(
                tournament_game__game__slug="valorant"
            ).team_name,
            "Blue Phoenix",
        )
        self.assertEqual(
            TournamentGame.objects.get(
                tournament__slug="dev-usec-current",
                game__slug="valorant",
            ).fee_amount,
            Decimal("50000.00"),
        )
        restored_payment = PaymentAttempt.objects.get(
            registration__submitted_by=player,
            registration__tournament_game__game__slug="valorant",
        )
        self.assertEqual(restored_payment.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(restored_payment.reference, "DEV-VAL-PENDING")
        self.assertTrue(
            Registration.objects.filter(pk=outsider_registration.pk).exists()
        )
        self.assertTrue(
            Tournament.objects.filter(pk=outsider_tournament.pk).exists()
        )

    def test_seed_failure_rolls_back_bootstrap_accounts_and_catalog(self):
        with patch(
            "registrations.dev_seed._seed_catalog",
            side_effect=ValidationError("forced failure"),
        ):
            with self.assertRaises(CommandError):
                self.run_seed()

        self.assertFalse(
            get_user_model().objects.filter(
                email__in=(
                    "player@email.com",
                    "organizer@email.com",
                    "admin@email.com",
                )
            ).exists()
        )
        self.assertFalse(Group.objects.filter(name="Organizers").exists())
        self.assertFalse(Tournament.objects.filter(slug__startswith="dev-usec-").exists())
```

Format the long `assertEqual` expression with Ruff after the implementation if Ruff chooses a different legal line break.

- [ ] **Step 2: Run the new tests and confirm registrations are missing**

Run:

```powershell
uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2
```

Expected: the registration matrix and rerun tests fail because no seeded registrations or payments exist, and the current Counter-Strike 2 state is `open` rather than `full`.

- [ ] **Step 3: Add domain-service imports and scenario summary constants**

Add these imports to `server/registrations/dev_seed.py` after the tournament imports:

```python
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
```

Add this constant after `SEED_TOURNAMENT_SLUGS`:

```python
SCENARIO_SUMMARY = (
    "Valorant: SUBMITTED / payment PENDING",
    "Chess: APPROVED / free registration",
    "Counter-Strike 2: UNDER_REVIEW / payment VERIFIED / capacity FULL",
    "Rocket League: REJECTED / rejected payment plus pending replacement",
    "League of Legends: registration NOT_OPEN",
    "Development draft: unpublished",
)
```

- [ ] **Step 4: Implement canonical registrations, payments, transitions, and timestamps**

Add these helpers before `seed_development_data` in `server/registrations/dev_seed.py`:

```python
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
            now - timedelta(days=67),
        ),
    )

    return valorant, chess, counter_strike, rocket_league
```

Replace `seed_development_data` with:

```python
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
```

- [ ] **Step 5: Print the deterministic scenario summary**

Change the import in `server/registrations/management/commands/seed_dev_data.py` to:

```python
from registrations.dev_seed import (
    ACCOUNT_CREDENTIALS,
    SCENARIO_SUMMARY,
    seed_development_data,
)
```

Add this output immediately after the tournament slug loop and before the rerun reminder:

```python
        self.stdout.write("Scenarios:")
        for scenario in SCENARIO_SUMMARY:
            self.stdout.write(f"  {scenario}")
```

- [ ] **Step 6: Run the complete command test module**

Run:

```powershell
uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2
```

Expected: `Ran 6 tests` and `OK`.

- [ ] **Step 7: Run existing domain and public API regression tests**

Run:

```powershell
uv run python manage.py test registrations.tests.test_services registrations.tests.test_management_command tournaments.tests.test_api -v 2
```

Expected: all selected existing tests pass with `OK`.

- [ ] **Step 8: Format and lint the seed implementation and tests**

Run:

```powershell
uv run ruff format registrations/dev_seed.py registrations/management/commands/seed_dev_data.py registrations/tests/test_seed_dev_data_command.py
uv run ruff check registrations/dev_seed.py registrations/management/commands/seed_dev_data.py registrations/tests/test_seed_dev_data_command.py
```

Expected: Ruff may report files reformatted, followed by `All checks passed!`.

- [ ] **Step 9: Commit the scenario implementation**

```powershell
git add server/registrations/dev_seed.py server/registrations/management/commands/seed_dev_data.py server/registrations/tests/test_seed_dev_data_command.py
git commit -m "feat: seed registration and payment scenarios" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Developer Documentation and Full Verification

**Files:**

- Modify: `server/README.md`

**Interfaces:**

- Consumes: final `seed_dev_data` command behavior from Tasks 1-3.
- Produces: copy-pasteable local usage, exact credentials, safety guidance, and rerun ownership documentation.

- [ ] **Step 1: Add the development seed documentation**

Append this section to `server/README.md`:

````markdown
## Development seed data

After applying migrations, create or restore the local testing scenarios with:

```powershell
uv run python manage.py seed_dev_data
```

The command creates predictable credentials and normally requires `DEBUG=True`. For an intentional non-production test database configured with `DEBUG=False`, the explicit override is:

```powershell
uv run python manage.py seed_dev_data --allow-non-debug
```

Never use the override against a production database.

Test accounts:

| Role | Email | Password |
| --- | --- | --- |
| Player | `player@email.com` | `player@123` |
| Organizer | `organizer@email.com` | `organizer@123` |
| Admin | `admin@email.com` | `admin@123` |

The organizer is a least-privilege staff member in the `Organizers` group. The admin is a separate superuser so organizer permission boundaries remain testable.

Seeded tournament slugs:

- `dev-usec-current`: open, full, and upcoming registration scenarios;
- `dev-usec-archive`: closed and rejected historical scenarios;
- `dev-usec-draft`: unpublished admin-only scenario.

Rerunning the command resets the three documented accounts, the `dev-usec-*` tournament configuration, and registrations owned by `player@email.com` within those tournaments. It does not flush the database, remove registrations submitted by other accounts, or modify unrelated tournaments.
````

- [ ] **Step 2: Confirm no model migration was introduced**

Run:

```powershell
uv run python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 3: Run Django system checks**

Run:

```powershell
uv run python manage.py check
```

Expected: `System check identified no issues (0 silenced).`.

- [ ] **Step 4: Run the complete backend test suite**

Run:

```powershell
uv run python manage.py test -v 2
```

Expected: all backend tests pass with a final `OK`.

- [ ] **Step 5: Run the complete backend lint check**

Run:

```powershell
uv run ruff check .
```

Expected: `All checks passed!`.

- [ ] **Step 6: Check whitespace and the exact working-tree scope**

Run from the repository root:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors. Only the planned seed implementation and README should be new or modified in addition to the user's pre-existing unrelated working-tree files.

- [ ] **Step 7: Commit the documentation**

```powershell
git add server/README.md
git commit -m "docs: document development seed data" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Inspect final branch history and status without changing files**

Run:

```powershell
git log -5 --oneline --decorate
git status --short
```

Expected: the design commit plus the three implementation commits and documentation commit are visible on `feat/development-seed-data`; unrelated pre-existing changes remain unstaged.
