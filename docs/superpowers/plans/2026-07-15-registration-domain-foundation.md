# Registration domain foundation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Django backend slice for tournament-game registration: the custom user, durable domain models, transactional registration guards, organizer administration, and participant ownership authorization.

**Architecture:** Create three Django apps: `accounts`, `tournaments`, and `registrations`. `Registration.submitted_by` is the source of participant ownership. DRF filters private querysets by that foreign key and uses small custom permission classes as defense in depth. Django Admin handles organizer workflows through domain services; it does not expose unrestricted ownership, roster, payment, history, or status edits.

**Tech Stack:** Python 3.12+, Django 6.0, Django REST Framework 3.17, PostgreSQL, Django's test runner, Ruff, uv, and mise.

## Global constraints

- The approved domain contract is [the registration domain model design](../specs/2026-07-15-registration-domain-model-design.md).
- Set `AUTH_USER_MODEL = "accounts.User"` before applying the first database migration.
- Do not implement SvelteKit screens, JWT token-issuance endpoints, public tournament read endpoints, brackets, or results in this slice.
- Keep the existing `guardian` dependency and backend configuration untouched, but do not call `assign_perm`, use `DjangoObjectPermissions`, or create Guardian permission rows. Direct ownership is sufficient for v1.
- Treat `Registration.submitted_by` as ownership. A manager may submit a team without becoming a roster member.
- Do not accept roster-account identifiers or create `RegistrationMember.user` links in this slice. Roster rows are immutable snapshots at submission time; account-linked player claims and duplicate-player enforcement require a later verified identity-claim flow.
- Filter list querysets as well as applying object permissions. Object permissions alone do not protect DRF lists or object creation.
- Preserve the existing uncommitted CORS setting change in `server/config/settings.py`.
- Run backend commands from `server/` with `uv run`; use `uv run python manage.py test`, `uv run python manage.py check`, and `uv run ruff check .`.

## File structure

| Path | Responsibility |
| --- | --- |
| `server/accounts/models.py` | Email-login custom `User` model and manager |
| `server/accounts/admin.py` | Safe Django Admin registration for users |
| `server/tournaments/models.py` | `Game`, `Tournament`, and `TournamentGame` models and local constraints |
| `server/tournaments/admin.py` | Tournament catalog administration |
| `server/registrations/models.py` | Registrations, members, payment attempts, and status events |
| `server/registrations/services.py` | Transactional submission, review, and payment commands |
| `server/registrations/permissions.py` | Ownership permission classes based on `submitted_by` |
| `server/registrations/serializers.py` | Participant-safe registration and payment input/output serializers |
| `server/registrations/views.py` | Private "My Registrations" list, detail, submission, and payment actions |
| `server/registrations/admin.py` | Organizer review UI and guarded admin actions |
| `server/registrations/management/commands/bootstrap_organizers.py` | Idempotent creation of the `Organizers` group and its model permissions |
| `server/config/settings.py` | Local-app registration, custom user setting, and development media storage |
| `server/config/urls.py` | API routing and debug-only media serving |
| `server/config/api_urls.py` | DRF router registration for participant registration endpoints |
| `server/*/tests/` | Isolated Django tests for models, guards, permissions, API, and setup command |

### Task 1: Establish the custom account model before any migrations

**Files:**

- Create: `server/accounts/__init__.py`
- Create: `server/accounts/apps.py`
- Create: `server/accounts/managers.py`
- Create: `server/accounts/models.py`
- Create: `server/accounts/admin.py`
- Create: `server/accounts/tests/__init__.py`
- Create: `server/accounts/tests/test_models.py`
- Create: `server/accounts/migrations/0001_initial.py` via `makemigrations`
- Modify: `server/config/settings.py`

**Interfaces:**

- Produces `accounts.User` with `email` as `USERNAME_FIELD`
- Produces `User.objects.create_user(email, password, **extra_fields)`
- Produces `settings.AUTH_USER_MODEL == "accounts.User"`

- [ ] **Step 1: Check whether a database has already applied auth migrations**

Run:

```powershell
cd server
uv run python manage.py showmigrations auth
```

Expected: no applied (`[X]`) migrations. If any are applied, stop this plan and create a separate migration strategy before changing `AUTH_USER_MODEL`; do not retrofit a custom user model into an existing migrated database.

- [ ] **Step 2: Write the failing user-model tests**

Create `server/accounts/tests/test_models.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.db import IntegrityError, transaction


class UserModelTests(TestCase):
    def test_email_is_the_login_identifier(self):
        user = get_user_model().objects.create_user(
            email="captain@example.com",
            password="strong-password",
            gamer_tag="captain",
            school="HCMUS",
        )

        self.assertEqual(get_user_model().USERNAME_FIELD, "email")
        self.assertEqual(user.email, "captain@example.com")
        self.assertTrue(user.check_password("strong-password"))

    def test_email_is_unique(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            email="same@example.com", password="strong-password"
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            user_model.objects.create_user(
                email="same@example.com", password="another-password"
            )
```

- [ ] **Step 3: Run the test to confirm the missing app fails**

Run:

```powershell
cd server
uv run python manage.py test accounts.tests.test_models -v 2
```

Expected: failure because the `accounts` app and custom user model do not exist.

- [ ] **Step 4: Create the app and custom user model**

Create `server/accounts/apps.py`:

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
```

Create `server/accounts/managers.py`:

```python
from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields["is_staff"] is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)
```

Create `server/accounts/models.py`:

```python
from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    gamer_tag = models.CharField(max_length=64, blank=True)
    school = models.CharField(max_length=128, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return self.email
```

Create `server/accounts/admin.py`:

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AccountUserAdmin(UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "gamer_tag", "school", "is_staff", "is_active")
    search_fields = ("email", "gamer_tag", "school")
    fieldsets = (
        (None, {"fields": ("email", "password")} ),
        ("Profile", {"fields": ("gamer_tag", "school")} ),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")} ),
        ("Important dates", {"fields": ("last_login", "date_joined")} ),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")} ),
    )
```

- [ ] **Step 5: Register the app and create its first migration**

In `server/config/settings.py`, add `accounts` to `INSTALLED_APPS` and set:

```python
AUTH_USER_MODEL = "accounts.User"
```

Run:

```powershell
cd server
uv run python manage.py makemigrations accounts
uv run python manage.py migrate
```

Expected: Django creates and applies `accounts.0001_initial` before tests create their test database.

- [ ] **Step 6: Run the user tests and Django checks**

Run:

```powershell
cd server
uv run python manage.py test accounts.tests.test_models -v 2
uv run python manage.py check
```

Expected: both commands exit `0`.

- [ ] **Step 7: Commit the custom-user foundation**

```powershell
git add server/accounts server/config/settings.py
git commit -m "feat: add email-based user model"
```

### Task 2: Model tournaments and their configured games

**Files:**

- Create: `server/tournaments/__init__.py`
- Create: `server/tournaments/apps.py`
- Create: `server/tournaments/models.py`
- Create: `server/tournaments/admin.py`
- Create: `server/tournaments/tests/__init__.py`
- Create: `server/tournaments/tests/test_models.py`
- Create: `server/tournaments/tests/test_admin.py`
- Create: `server/tournaments/migrations/0001_initial.py` via `makemigrations`
- Modify: `server/config/settings.py`

**Interfaces:**

- Produces `Game`, `Tournament`, and `TournamentGame`
- Produces `TournamentGame.is_team` and `TournamentGame.is_individual` derived properties
- Produces one database row per `(tournament, game)` pair

- [ ] **Step 1: Write failing tournament-model tests**

Create `server/tournaments/tests/test_models.py`:

```python
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from tournaments.models import Game, Tournament, TournamentGame


class TournamentGameModelTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(name="Valorant", slug="valorant")
        self.tournament = Tournament.objects.create(
            name="USEC Summer 2026", slug="usec-summer-2026"
        )

    def test_tournament_has_one_configuration_per_game(self):
        TournamentGame.objects.create(
            tournament=self.tournament,
            game=self.game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=7),
            fee_amount="50000.00",
            fee_currency="VND",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            TournamentGame.objects.create(
                tournament=self.tournament,
                game=self.game,
                team_size_min=5,
                team_size_max=5,
                registration_opens_at=timezone.now(),
                registration_closes_at=timezone.now() + timedelta(days=7),
                fee_amount="50000.00",
                fee_currency="VND",
            )

    def test_exact_five_player_game_is_a_team_game(self):
        tournament_game = TournamentGame.objects.create(
            tournament=self.tournament,
            game=self.game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=7),
            fee_amount="0.00",
            fee_currency="VND",
        )

        self.assertTrue(tournament_game.is_team)
        self.assertFalse(tournament_game.is_individual)
```

- [ ] **Step 2: Run the test to confirm the app is absent**

Run:

```powershell
cd server
uv run python manage.py test tournaments.tests -v 2
```

Expected: failure because `tournaments` is not installed.

- [ ] **Step 3: Implement the catalog and configuration models**

Create `server/tournaments/apps.py`:

```python
from django.apps import AppConfig


class TournamentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tournaments"
```

Create `server/tournaments/models.py`:

```python
from django.db import models
from django.db.models import F, Q


class Game(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Tournament(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(starts_at__isnull=True)
                    | Q(ends_at__isnull=True)
                    | Q(starts_at__lt=F("ends_at"))
                ),
                name="tournament_starts_before_ends",
            )
        ]

    def __str__(self) -> str:
        return self.name


class TournamentGame(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="tournament_games"
    )
    game = models.ForeignKey(
        Game, on_delete=models.PROTECT, related_name="tournament_games"
    )
    team_size_min = models.PositiveSmallIntegerField()
    team_size_max = models.PositiveSmallIntegerField()
    registration_opens_at = models.DateTimeField()
    registration_closes_at = models.DateTimeField()
    registration_capacity = models.PositiveIntegerField(null=True, blank=True)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee_currency = models.CharField(max_length=3, default="VND")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tournament", "game"),
                name="unique_tournament_game",
            ),
            models.CheckConstraint(
                condition=Q(team_size_min__gte=1),
                name="tournament_game_min_team_size_positive",
            ),
            models.CheckConstraint(
                condition=Q(team_size_max__gte=F("team_size_min")),
                name="tournament_game_max_team_size_at_least_min",
            ),
            models.CheckConstraint(
                condition=Q(registration_opens_at__lt=F("registration_closes_at")),
                name="tournament_game_registration_window_valid",
            ),
            models.CheckConstraint(
                condition=Q(registration_capacity__isnull=True)
                | Q(registration_capacity__gt=0),
                name="tournament_game_capacity_positive_or_null",
            ),
            models.CheckConstraint(
                condition=Q(fee_amount__gte=0),
                name="tournament_game_fee_non_negative",
            ),
        ]

    @property
    def is_individual(self) -> bool:
        return self.team_size_min == self.team_size_max == 1

    @property
    def is_team(self) -> bool:
        return self.team_size_max > 1

    def __str__(self) -> str:
        return f"{self.tournament} / {self.game}"
```

Create `server/tournaments/admin.py`:

```python
from django.contrib import admin

from .models import Game, Tournament, TournamentGame


def _is_organizer_staff(user) -> bool:
    return user.is_authenticated and (
        user.is_superuser
        or (user.is_staff and user.groups.filter(name="Organizers").exists())
    )


class OrganizerStaffAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return _is_organizer_staff(request.user) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return _is_organizer_staff(request.user) and super().has_view_permission(
            request, obj
        )

    def has_change_permission(self, request, obj=None):
        return _is_organizer_staff(request.user) and super().has_change_permission(
            request, obj
        )


@admin.register(Game)
class GameAdmin(OrganizerStaffAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tournament)
class TournamentAdmin(OrganizerStaffAdmin):
    list_display = ("name", "slug", "starts_at", "ends_at", "is_published")
    list_filter = ("is_published",)
    search_fields = ("name", "slug", "location")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TournamentGame)
class TournamentGameAdmin(OrganizerStaffAdmin):
    list_display = (
        "tournament",
        "game",
        "team_size_min",
        "team_size_max",
        "registration_opens_at",
        "registration_closes_at",
        "registration_capacity",
        "fee_amount",
        "fee_currency",
    )
    list_filter = ("tournament", "game", "fee_currency")
    search_fields = ("tournament__name", "tournament__slug", "game__name", "game__slug")
    date_hierarchy = "registration_opens_at"
```

Create `server/tournaments/tests/test_admin.py`:

```python
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase

from tournaments.admin import GameAdmin
from tournaments.models import Game


class TournamentAdminAccessTests(TestCase):
    def test_direct_catalog_permissions_do_not_bypass_organizer_membership(self):
        staff_user = get_user_model().objects.create_user(
            email="catalog-staff@example.com",
            password="strong-password",
            is_staff=True,
        )
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="tournaments", codename="view_game"
            ),
            Permission.objects.get(
                content_type__app_label="tournaments", codename="change_game"
            ),
        )
        game = Game.objects.create(name="Chess", slug="chess")
        request = RequestFactory().get("/admin/tournaments/game/")
        request.user = staff_user
        model_admin = GameAdmin(Game, AdminSite())

        self.assertFalse(model_admin.has_module_permission(request))
        self.assertFalse(model_admin.has_view_permission(request, game))
        self.assertFalse(model_admin.has_change_permission(request, game))
```

- [ ] **Step 4: Register the app and create migration**

Add `tournaments` to `INSTALLED_APPS`, then run:

```powershell
cd server
uv run python manage.py makemigrations tournaments
uv run python manage.py migrate
```

- [ ] **Step 5: Run the tournament tests**

Run:

```powershell
cd server
uv run python manage.py test tournaments.tests -v 2
```

Expected: model constraints, derived team type, and the Organizer-only catalog Admin gate all pass.

- [ ] **Step 6: Commit the tournament model slice**

```powershell
git add server/tournaments server/config/settings.py
git commit -m "feat: add tournament game configuration"
```

### Task 3: Persist registrations, roster snapshots, payments, and status history

**Files:**

- Create: `server/registrations/__init__.py`
- Create: `server/registrations/apps.py`
- Create: `server/registrations/models.py`
- Create: `server/registrations/admin.py`
- Create: `server/registrations/tests/__init__.py`
- Create: `server/registrations/tests/test_models.py`
- Create: `server/registrations/migrations/0001_initial.py` via `makemigrations`
- Modify: `server/config/settings.py`
- Modify: `server/config/urls.py`

**Interfaces:**

- Produces `Registration`, `RegistrationMember`, `PaymentAttempt`, and `RegistrationStatusEvent`
- Produces `Registration.Status` and `PaymentAttempt.Status` enums
- Produces `Registration.active_statuses()` for capacity and future verified-player-claim queries

- [ ] **Step 1: Write failing persistence tests**

Create `server/registrations/tests/test_models.py`:

```python
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from registrations.models import Registration, RegistrationMember
from tournaments.models import Game, Tournament, TournamentGame


class RegistrationMemberModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="captain@example.com", password="strong-password"
        )
        game = Game.objects.create(name="Valorant", slug="valorant")
        tournament = Tournament.objects.create(name="Summer", slug="summer")
        self.tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        self.registration = Registration.objects.create(
            tournament_game=self.tournament_game,
            submitted_by=self.user,
            team_name="USEC",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot="0.00",
            fee_currency_snapshot="VND",
            submitted_at=timezone.now(),
        )

    def test_only_one_captain_is_allowed_per_registration(self):
        RegistrationMember.objects.create(
            registration=self.registration,
            gamer_tag_snapshot="captain",
            school_snapshot="HCMUS",
            is_captain=True,
            display_order=1,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistrationMember.objects.create(
                registration=self.registration,
                gamer_tag_snapshot="second-captain",
                school_snapshot="HCMUS",
                is_captain=True,
                display_order=2,
            )
```

- [ ] **Step 2: Run the test to confirm the models are absent**

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_models -v 2
```

Expected: failure because `registrations` is not installed.

- [ ] **Step 3: Implement the registration models**

Create `server/registrations/apps.py`:

```python
from django.apps import AppConfig


class RegistrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "registrations"
```

Create `server/registrations/models.py`:

```python
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from tournaments.models import TournamentGame


class Registration(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    tournament_game = models.ForeignKey(
        TournamentGame, on_delete=models.PROTECT, related_name="registrations"
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_registrations",
    )
    team_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    fee_amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    fee_currency_snapshot = models.CharField(max_length=3)
    submitted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def active_statuses(cls) -> tuple[str, ...]:
        return (cls.Status.SUBMITTED, cls.Status.UNDER_REVIEW, cls.Status.APPROVED)


class RegistrationMember(models.Model):
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_registration_memberships",
    )
    gamer_tag_snapshot = models.CharField(max_length=64)
    school_snapshot = models.CharField(max_length=128)
    is_captain = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("display_order", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("registration",),
                condition=Q(is_captain=True),
                name="one_captain_per_registration",
            ),
            models.UniqueConstraint(
                fields=("registration", "display_order"),
                name="unique_member_display_order",
            ),
        ]


class PaymentAttempt(models.Model):
    class Method(models.TextChoices):
        MANUAL_PROOF = "MANUAL_PROOF", "Manual proof"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="payment_attempts"
    )
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    proof_file = models.FileField(upload_to="payment-proofs/%Y/%m/", blank=True)
    reference = models.CharField(max_length=128, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_payment_attempts",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RegistrationStatusEvent(models.Model):
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="status_events"
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, choices=Registration.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registration_status_events",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
```

- [ ] **Step 4: Configure local development media and migrate**

Add `registrations` to `INSTALLED_APPS` and add these settings without changing the existing CORS entries:

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

In `server/config/urls.py`, append the debug-only development route:

```python
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

Run:

```powershell
cd server
uv run python manage.py makemigrations registrations
uv run python manage.py migrate
```

- [ ] **Step 5: Run persistence tests**

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_models -v 2
```

Expected: the conditional captain uniqueness test passes.

- [ ] **Step 6: Commit persistence models**

```powershell
git add server/registrations server/config/settings.py server/config/urls.py
git commit -m "feat: add registration domain models"
```

### Task 4: Implement transactional registration and review commands

**Files:**

- Create: `server/registrations/services.py`
- Create: `server/registrations/tests/test_services.py`

**Interfaces:**

- Produces `RegistrationMemberInput`
- Produces `submit_registration`, `start_review`, `approve_registration`, `reject_registration`, `submit_payment_attempt`, and `review_payment_attempt`
- Every command receives the acting user explicitly

- [ ] **Step 1: Write failing service tests for the high-risk guards**

Create `server/registrations/tests/test_services.py`:

```python
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from registrations.models import PaymentAttempt, Registration
from registrations.services import (
    RegistrationMemberInput,
    reject_registration,
    review_payment_attempt,
    start_review,
    submit_payment_attempt,
    submit_registration,
)
from tournaments.models import Game, Tournament, TournamentGame


class SubmissionServiceTests(TestCase):
    def setUp(self):
        self.captain = get_user_model().objects.create_user(
            email="captain@example.com", password="strong-password"
        )
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(name="Summer", slug="summer")
        self.tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            team_size_min=1,
            team_size_max=1,
            registration_opens_at=timezone.now() - timedelta(minutes=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            registration_capacity=1,
            fee_amount="0.00",
            fee_currency="VND",
        )

    def test_submission_snapshots_profile_values_and_creates_event(self):
        registration = submit_registration(
            submitted_by=self.captain,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            members=[
                RegistrationMemberInput(
                    gamer_tag_snapshot="captain",
                    school_snapshot="HCMUS",
                    is_captain=True,
                    display_order=1,
                )
            ],
        )

        self.assertEqual(registration.members.get().gamer_tag_snapshot, "captain")
        self.assertEqual(registration.status_events.get().to_status, "SUBMITTED")

    def test_capacity_blocks_a_second_active_entry(self):
        member = RegistrationMemberInput(
            gamer_tag_snapshot="captain",
            school_snapshot="HCMUS",
            is_captain=True,
            display_order=1,
        )
        submit_registration(
            submitted_by=self.captain,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            members=[member],
        )

        with self.assertRaises(ValidationError):
            submit_registration(
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="",
                members=[member],
            )
```

- [ ] **Step 2: Run the service test to confirm the module is absent**

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_services -v 2
```

Expected: failure because `registrations.services` does not exist.

- [ ] **Step 3: Implement the command boundary**

Create `server/registrations/services.py` with this public interface and validation order:

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import PaymentAttempt, Registration, RegistrationMember, RegistrationStatusEvent
from tournaments.models import TournamentGame


@dataclass(frozen=True)
class RegistrationMemberInput:
    gamer_tag_snapshot: str
    school_snapshot: str
    is_captain: bool
    display_order: int


def submit_registration(*, submitted_by, tournament_game_id: int, team_name: str, members: Sequence[RegistrationMemberInput]) -> Registration:
    with transaction.atomic():
        tournament_game = TournamentGame.objects.select_for_update().get(pk=tournament_game_id)
        now = timezone.now()
        if not tournament_game.registration_opens_at <= now < tournament_game.registration_closes_at:
            raise ValidationError("Registration is not open.")

        active = Registration.objects.filter(
            tournament_game=tournament_game,
            status__in=Registration.active_statuses(),
        )
        if tournament_game.registration_capacity is not None and active.count() >= tournament_game.registration_capacity:
            raise ValidationError("Registration capacity has been reached.")

        _validate_roster(tournament_game=tournament_game, team_name=team_name, members=members)

        registration = Registration.objects.create(
            tournament_game=tournament_game,
            submitted_by=submitted_by,
            team_name=team_name.strip(),
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=tournament_game.fee_amount,
            fee_currency_snapshot=tournament_game.fee_currency,
        )
        RegistrationMember.objects.bulk_create(
            [
                RegistrationMember(
                    registration=registration,
                    gamer_tag_snapshot=member.gamer_tag_snapshot.strip(),
                    school_snapshot=member.school_snapshot.strip(),
                    is_captain=member.is_captain,
                    display_order=member.display_order,
                )
                for member in members
            ]
        )
        RegistrationStatusEvent.objects.create(
            registration=registration,
            from_status="",
            to_status=Registration.Status.SUBMITTED,
            actor=submitted_by,
        )
        return registration
```

Append these helpers and commands to the same module. They are the only approved mutation paths for submission, organizer review status, and payment attempts; submitted roster snapshots are immutable in this slice:

```python
def _validate_roster(
    *,
    tournament_game: TournamentGame,
    team_name: str,
    members: Sequence[RegistrationMemberInput],
) -> None:
    if not tournament_game.team_size_min <= len(members) <= tournament_game.team_size_max:
        raise ValidationError("Roster size is outside the configured limit.")
    if sum(member.is_captain for member in members) != 1:
        raise ValidationError("A registration must have exactly one captain.")
    if bool(team_name.strip()) != tournament_game.is_team:
        raise ValidationError("A team name is required exactly for team games.")
    if any(member.display_order < 1 for member in members):
        raise ValidationError("Roster display order must start at one.")
    if len({member.display_order for member in members}) != len(members):
        raise ValidationError("Roster display order must be unique.")
    if any(
        not member.gamer_tag_snapshot.strip() or not member.school_snapshot.strip()
        for member in members
    ):
        raise ValidationError("Every player needs a gamer tag and school snapshot.")


def _require_organizer(actor, permission: str) -> None:
    if actor.is_authenticated and actor.is_superuser:
        return
    if (
        actor.is_authenticated
        and actor.is_staff
        and actor.groups.filter(name="Organizers").exists()
        and actor.has_perm(permission)
    ):
        return
    raise PermissionDenied("An Organizer staff account is required.")


def _transition_registration(
    *,
    actor,
    registration_id: int,
    expected_status: str,
    to_status: str,
    note: str = "",
) -> Registration:
    _require_organizer(actor, "registrations.change_registration")
    with transaction.atomic():
        registration = Registration.objects.select_for_update().get(pk=registration_id)
        if registration.status != expected_status:
            raise ValidationError(
                f"Cannot move a {registration.status} registration to {to_status}."
            )
        registration.status = to_status
        registration.save(update_fields=("status", "updated_at"))
        RegistrationStatusEvent.objects.create(
            registration=registration,
            from_status=expected_status,
            to_status=to_status,
            actor=actor,
            note=note.strip(),
        )
        return registration


def start_review(*, actor, registration_id: int, note: str = "") -> Registration:
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.SUBMITTED,
        to_status=Registration.Status.UNDER_REVIEW,
        note=note,
    )


def approve_registration(*, actor, registration_id: int, note: str = "") -> Registration:
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.UNDER_REVIEW,
        to_status=Registration.Status.APPROVED,
        note=note,
    )


def reject_registration(*, actor, registration_id: int, note: str) -> Registration:
    if not note.strip():
        raise ValidationError("A rejection reason is required.")
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.UNDER_REVIEW,
        to_status=Registration.Status.REJECTED,
        note=note,
    )


def submit_payment_attempt(
    *,
    actor,
    registration_id: int,
    amount: Decimal,
    currency: str,
    proof_file=None,
    reference: str = "",
) -> PaymentAttempt:
    with transaction.atomic():
        registration = Registration.objects.select_for_update().get(pk=registration_id)
        if registration.submitted_by_id != actor.pk:
            raise PermissionDenied("Only the submitter can add a payment attempt.")
        if registration.fee_amount_snapshot <= Decimal("0.00"):
            raise ValidationError("This registration has no payment due.")
        if amount != registration.fee_amount_snapshot:
            raise ValidationError("Payment amount must match the registration fee.")
        if currency.upper() != registration.fee_currency_snapshot:
            raise ValidationError("Payment currency must match the registration fee.")
        if proof_file is None and not reference.strip():
            raise ValidationError("Provide either a payment proof file or a reference.")

        return PaymentAttempt.objects.create(
            registration=registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            status=PaymentAttempt.Status.PENDING,
            amount=amount,
            currency=currency.upper(),
            proof_file=proof_file,
            reference=reference.strip(),
        )


def review_payment_attempt(
    *,
    actor,
    payment_attempt_id: int,
    status: str,
    note: str = "",
) -> PaymentAttempt:
    _require_organizer(actor, "registrations.change_paymentattempt")
    if status not in {PaymentAttempt.Status.VERIFIED, PaymentAttempt.Status.REJECTED}:
        raise ValidationError("A payment attempt may only be verified or rejected.")

    with transaction.atomic():
        payment_attempt = PaymentAttempt.objects.select_for_update().get(pk=payment_attempt_id)
        if payment_attempt.status != PaymentAttempt.Status.PENDING:
            raise ValidationError("Only a pending payment attempt may be reviewed.")
        payment_attempt.status = status
        payment_attempt.reviewed_by = actor
        payment_attempt.reviewed_at = timezone.now()
        payment_attempt.review_note = note.strip()
        payment_attempt.save(
            update_fields=("status", "reviewed_by", "reviewed_at", "review_note")
        )
        return payment_attempt
```

`submit_registration` must store `team_name.strip()` and snapshot strings stripped of surrounding whitespace when it creates immutable `RegistrationMember` rows with `user=None`. It creates exactly one `RegistrationStatusEvent`; payment reviews do not change a registration status.

- [ ] **Step 4: Add tests for remaining command branches**

Append these concrete methods to `SubmissionServiceTests`:

```python
    def _member(self, *, gamer_tag="captain", is_captain=True, display_order=1):
        return RegistrationMemberInput(
            gamer_tag_snapshot=gamer_tag,
            school_snapshot="HCMUS",
            is_captain=is_captain,
            display_order=display_order,
        )

    def _submit_solo(self):
        return submit_registration(
            submitted_by=self.captain,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            members=[self._member()],
        )

    def test_roster_rejects_non_positive_display_order(self):
        with self.assertRaises(ValidationError):
            submit_registration(
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="",
                members=[self._member(display_order=0)],
            )

    def test_closed_registration_window_is_rejected(self):
        self.tournament_game.registration_closes_at = timezone.now() - timedelta(seconds=1)
        self.tournament_game.save(update_fields=("registration_closes_at",))

        with self.assertRaises(ValidationError):
            self._submit_solo()

    def test_roster_requires_exactly_one_captain(self):
        self.tournament_game.team_size_min = 2
        self.tournament_game.team_size_max = 2
        self.tournament_game.registration_capacity = None
        self.tournament_game.save(
            update_fields=("team_size_min", "team_size_max", "registration_capacity")
        )

        with self.assertRaises(ValidationError):
            submit_registration(
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="USEC",
                members=[
                    self._member(gamer_tag="one", is_captain=False),
                    self._member(gamer_tag="two", is_captain=False, display_order=2),
                ],
            )
        with self.assertRaises(ValidationError):
            submit_registration(
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="USEC",
                members=[
                    self._member(gamer_tag="one"),
                    self._member(gamer_tag="two", display_order=2),
                ],
            )

    def test_manager_may_submit_a_team_without_becoming_a_member(self):
        manager = get_user_model().objects.create_user(
            email="manager@example.com", password="strong-password"
        )
        self.tournament_game.team_size_min = 2
        self.tournament_game.team_size_max = 2
        self.tournament_game.registration_capacity = None
        self.tournament_game.save(
            update_fields=("team_size_min", "team_size_max", "registration_capacity")
        )

        registration = submit_registration(
            submitted_by=manager,
            tournament_game_id=self.tournament_game.pk,
            team_name="USEC",
            members=[
                self._member(gamer_tag="one"),
                self._member(gamer_tag="two", is_captain=False, display_order=2),
            ],
        )

        self.assertEqual(registration.submitted_by, manager)
        self.assertIsNone(registration.members.get(display_order=1).user)

    def test_zero_fee_registration_rejects_payment_attempt(self):
        registration = self._submit_solo()

        with self.assertRaises(ValidationError):
            submit_payment_attempt(
                actor=self.captain,
                registration_id=registration.pk,
                amount=Decimal("0.00"),
                currency="VND",
                reference="no-charge",
            )

    def test_payment_review_never_changes_registration_status(self):
        self.tournament_game.fee_amount = Decimal("50000.00")
        self.tournament_game.save(update_fields=("fee_amount",))
        registration = self._submit_solo()
        organizer = get_user_model().objects.create_user(
            email="organizer@example.com",
            password="strong-password",
            is_staff=True,
        )
        organizers, _ = Group.objects.get_or_create(name="Organizers")
        organizer.groups.add(organizers)
        organizer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="registrations",
                codename="change_paymentattempt",
            )
        )
        attempt = submit_payment_attempt(
            actor=self.captain,
            registration_id=registration.pk,
            amount=Decimal("50000.00"),
            currency="VND",
            reference="bank-transfer-123",
        )

        review_payment_attempt(
            actor=organizer,
            payment_attempt_id=attempt.pk,
            status=PaymentAttempt.Status.VERIFIED,
        )
        registration.refresh_from_db()

        self.assertEqual(registration.status, Registration.Status.SUBMITTED)

    def test_staff_user_needs_organizers_group_and_model_permission_to_review(self):
        registration = self._submit_solo()
        staff_user = get_user_model().objects.create_user(
            email="staff@example.com", password="strong-password", is_staff=True
        )
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="registrations",
                codename="change_registration",
            )
        )

        with self.assertRaises(PermissionDenied):
            start_review(actor=staff_user, registration_id=registration.pk)

        organizers, _ = Group.objects.get_or_create(name="Organizers")
        staff_user.groups.add(organizers)
        start_review(actor=staff_user, registration_id=registration.pk)
        registration.refresh_from_db()

        self.assertEqual(registration.status, Registration.Status.UNDER_REVIEW)
        with self.assertRaises(ValidationError):
            reject_registration(
                actor=staff_user, registration_id=registration.pk, note=""
            )
        reject_registration(
            actor=staff_user,
            registration_id=registration.pk,
            note="Player is already registered.",
        )
        event = registration.status_events.get(to_status=Registration.Status.REJECTED)
        self.assertEqual(event.note, "Player is already registered.")
```

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_services -v 2
```

Expected: every guard test passes.

- [ ] **Step 5: Commit the transactional domain layer**

```powershell
git add server/registrations/services.py server/registrations/tests/test_services.py
git commit -m "feat: add guarded registration services"
```

### Task 5: Enforce participant ownership in DRF without Guardian rows

**Files:**

- Create: `server/registrations/permissions.py`
- Create: `server/registrations/serializers.py`
- Create: `server/registrations/views.py`
- Create: `server/registrations/urls.py`
- Create: `server/registrations/tests/test_api.py`
- Create: `server/config/api_urls.py`
- Modify: `server/config/urls.py`

**Interfaces:**

- Produces `IsRegistrationSubmitter` as defense in depth for owned registration retrievals
- Produces `RegistrationViewSet` at `/api/registrations/`
- Produces `POST /api/registrations/submit/` and `POST /api/registrations/{id}/payment-attempts/`
- Produces private list/detail views that only return registrations submitted by the authenticated caller

- [ ] **Step 1: Write failing ownership and information-boundary tests**

Create `server/registrations/tests/test_api.py`:

```python
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from registrations.models import Registration
from tournaments.models import Game, Tournament, TournamentGame


@override_settings(ROOT_URLCONF="config.urls")
class RegistrationOwnershipApiTests(APITestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            email="owner@example.com", password="strong-password"
        )
        self.other_user = get_user_model().objects.create_user(
            email="other@example.com", password="strong-password"
        )
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(name="Summer", slug="summer")
        self.tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            team_size_min=1,
            team_size_max=1,
            registration_opens_at=timezone.now() - timedelta(minutes=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount=Decimal("50000.00"),
            fee_currency="VND",
        )
        self.registration = self._create_registration(self.owner)
        self._create_registration(self.other_user)

    def _create_registration(self, owner):
        return Registration.objects.create(
            tournament_game=self.tournament_game,
            submitted_by=owner,
            team_name="",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=Decimal("50000.00"),
            fee_currency_snapshot="VND",
        )

    def _submission_payload(self):
        return {
            "tournament_game": self.tournament_game.pk,
            "team_name": "",
            "members": [
                {
                    "gamer_tag_snapshot": "captain",
                    "school_snapshot": "HCMUS",
                    "is_captain": True,
                    "display_order": 1,
                }
            ],
        }

    def test_unauthenticated_list_and_detail_are_not_available(self):
        list_response = self.client.get("/api/registrations/")
        detail_response = self.client.get(f"/api/registrations/{self.registration.pk}/")

        self.assertIn(list_response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})
        self.assertIn(detail_response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

    def test_owner_lists_and_retrieves_only_own_registration(self):
        self.client.force_authenticate(user=self.owner)

        list_response = self.client.get("/api/registrations/")
        detail_response = self.client.get(f"/api/registrations/{self.registration.pk}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual({item["id"] for item in list_response.data}, {self.registration.pk})
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertNotIn("submitted_by", detail_response.data)
        self.assertNotIn("payment_attempts", detail_response.data)

    def test_other_user_gets_404_for_a_foreign_registration(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(f"/api/registrations/{self.registration.pk}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_sets_the_owner_from_request_user(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            "/api/registrations/submit/", self._submission_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertEqual(registration.submitted_by, self.owner)
        self.assertIsNone(registration.members.get().user)

    def test_service_validation_errors_become_http_400(self):
        self.client.force_authenticate(user=self.owner)
        invalid_submission = self._submission_payload()
        invalid_submission["team_name"] = "not-valid-for-a-solo-game"

        submission_response = self.client.post(
            "/api/registrations/submit/", invalid_submission, format="json"
        )
        payment_response = self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            {"amount": "1.00", "currency": "VND", "reference": "wrong-amount"},
            format="json",
        )

        self.assertEqual(submission_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(payment_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_rejects_client_supplied_owner_or_player_account_fields(self):
        self.client.force_authenticate(user=self.owner)
        owner_payload = self._submission_payload()
        owner_payload["submitted_by"] = self.other_user.pk
        member_payload = self._submission_payload()
        member_payload["members"][0]["user_id"] = self.other_user.pk

        owner_response = self.client.post(
            "/api/registrations/submit/", owner_payload, format="json"
        )
        member_response = self.client.post(
            "/api/registrations/submit/", member_payload, format="json"
        )

        self.assertEqual(owner_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("submitted_by", owner_response.data)
        self.assertEqual(member_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("members", member_response.data)

    def test_other_user_cannot_add_a_payment_attempt_to_foreign_registration(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            {"amount": "50000.00", "currency": "VND", "reference": "transfer-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
```
- [ ] **Step 2: Run the API test to confirm routes are absent**

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_api -v 2
```

Expected: failure because `/api/registrations/` is not routed.

- [ ] **Step 3: Implement owner-filtered routes and explicit serializer allowlists**

Create `server/registrations/permissions.py`:

```python
from rest_framework.permissions import BasePermission


class IsRegistrationSubmitter(BasePermission):
    message = "You can only access registrations you submitted."

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.submitted_by_id == request.user.id
```

Create `server/registrations/serializers.py`:

```python
from rest_framework import serializers

from .models import PaymentAttempt, Registration, RegistrationMember, RegistrationStatusEvent
from .services import RegistrationMemberInput
from tournaments.models import TournamentGame


class TournamentGameSummarySerializer(serializers.ModelSerializer):
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    game_name = serializers.CharField(source="game.name", read_only=True)

    class Meta:
        model = TournamentGame
        fields = (
            "id",
            "tournament_name",
            "game_name",
            "team_size_min",
            "team_size_max",
            "fee_amount",
            "fee_currency",
        )


class RegistrationMemberReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationMember
        fields = ("gamer_tag_snapshot", "school_snapshot", "is_captain", "display_order")


class RegistrationStatusEventReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationStatusEvent
        fields = ("to_status", "created_at")


class RegistrationReadSerializer(serializers.ModelSerializer):
    tournament_game = TournamentGameSummarySerializer(read_only=True)
    members = RegistrationMemberReadSerializer(many=True, read_only=True)
    status_events = RegistrationStatusEventReadSerializer(many=True, read_only=True)

    class Meta:
        model = Registration
        fields = (
            "id",
            "tournament_game",
            "team_name",
            "status",
            "fee_amount_snapshot",
            "fee_currency_snapshot",
            "submitted_at",
            "members",
            "status_events",
        )


class StrictFieldsSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            return super().to_internal_value(data)
        unknown_fields = set(data.keys()) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError(
                {field: "This field is not allowed." for field in sorted(unknown_fields)}
            )
        return super().to_internal_value(data)


class RegistrationMemberSubmissionSerializer(StrictFieldsSerializer):
    gamer_tag_snapshot = serializers.CharField(max_length=64)
    school_snapshot = serializers.CharField(max_length=128)
    is_captain = serializers.BooleanField()
    display_order = serializers.IntegerField(min_value=1)


class RegistrationSubmissionSerializer(StrictFieldsSerializer):
    tournament_game = serializers.PrimaryKeyRelatedField(
        queryset=TournamentGame.objects.all()
    )
    team_name = serializers.CharField(max_length=100, allow_blank=True)
    members = RegistrationMemberSubmissionSerializer(many=True)

    def to_member_inputs(self) -> list[RegistrationMemberInput]:
        return [
            RegistrationMemberInput(**member)
            for member in self.validated_data["members"]
        ]


class PaymentAttemptSubmissionSerializer(StrictFieldsSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    proof_file = serializers.FileField(required=False, allow_null=True)
    reference = serializers.CharField(max_length=128, allow_blank=True, required=False)


class PaymentAttemptReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAttempt
        fields = ("id", "status", "amount", "currency", "created_at")
```

Create `server/registrations/views.py`:

```python
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Registration
from .permissions import IsRegistrationSubmitter
from .serializers import (
    PaymentAttemptReceiptSerializer,
    PaymentAttemptSubmissionSerializer,
    RegistrationReadSerializer,
    RegistrationSubmissionSerializer,
)
from .services import submit_payment_attempt, submit_registration


def _as_drf_validation_error(error: DjangoValidationError) -> DRFValidationError:
    if error.error_dict:
        return DRFValidationError(error.message_dict)
    return DRFValidationError(error.messages)


class RegistrationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsRegistrationSubmitter]
    serializer_class = RegistrationReadSerializer

    def get_queryset(self):
        return (
            Registration.objects.filter(submitted_by=self.request.user)
            .select_related("tournament_game__tournament", "tournament_game__game")
            .prefetch_related("members", "status_events")
        )

    @action(detail=False, methods=["post"], url_path="submit")
    def submit(self, request):
        serializer = RegistrationSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            registration = submit_registration(
                submitted_by=request.user,
                tournament_game_id=serializer.validated_data["tournament_game"].pk,
                team_name=serializer.validated_data["team_name"],
                members=serializer.to_member_inputs(),
            )
        except DjangoValidationError as error:
            raise _as_drf_validation_error(error) from error
        return Response(
            RegistrationReadSerializer(
                registration, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="payment-attempts")
    def payment_attempts(self, request, pk=None):
        registration = self.get_object()
        serializer = PaymentAttemptSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment_attempt = submit_payment_attempt(
                actor=request.user,
                registration_id=registration.pk,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            raise _as_drf_validation_error(error) from error
        return Response(
            PaymentAttemptReceiptSerializer(payment_attempt).data,
            status=status.HTTP_201_CREATED,
        )
```

Create `server/registrations/urls.py`:

```python
from rest_framework.routers import SimpleRouter

from .views import RegistrationViewSet

router = SimpleRouter()
router.register("registrations", RegistrationViewSet, basename="registration")
urlpatterns = router.urls
```

Create `server/config/api_urls.py`:

```python
from django.urls import include, path

urlpatterns = [path("", include("registrations.urls"))]
```

Update `server/config/urls.py` so its URL patterns include both the admin and the private API, while retaining the Task 3 debug-media block:

```python
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```
- [ ] **Step 4: Run the complete API authorization coverage**

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_api -v 2
```

Expected: unauthenticated calls are rejected; list and detail queries are owner-filtered; a submitted owner cannot be supplied by the client; roster account links are rejected; and a foreign payment-attempt request returns `404` without any Guardian `assign_perm` call.
- [ ] **Step 5: Commit the private API and permission layer**

```powershell
git add server/registrations/permissions.py server/registrations/serializers.py server/registrations/views.py server/registrations/urls.py server/registrations/tests server/config/api_urls.py server/config/urls.py
git commit -m "feat: enforce registration ownership in api"
```

### Task 6: Add guarded organizer administration and the Organizer group bootstrap command

**Files:**

- Modify: `server/registrations/admin.py`
- Create: `server/registrations/management/__init__.py`
- Create: `server/registrations/management/commands/__init__.py`
- Create: `server/registrations/management/commands/bootstrap_organizers.py`
- Create: `server/registrations/tests/test_management_command.py`
- Create: `server/registrations/tests/test_admin_actions.py`

**Interfaces:**

- Produces `bootstrap_organizers` management command
- Produces a least-privilege `Organizers` group: catalog add/change/view, registration and payment view/change, and roster/status-event view only
- Produces read-only registration evidence/history views and Admin actions that call domain services rather than assigning ownership, roster, payment, or status fields directly

- [ ] **Step 1: Write failing least-privilege group-bootstrap tests**

Create `server/registrations/tests/test_management_command.py`:

```python
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase


class BootstrapOrganizersCommandTests(TestCase):
    expected_permissions = {
        "tournaments.add_game",
        "tournaments.change_game",
        "tournaments.view_game",
        "tournaments.add_tournament",
        "tournaments.change_tournament",
        "tournaments.view_tournament",
        "tournaments.add_tournamentgame",
        "tournaments.change_tournamentgame",
        "tournaments.view_tournamentgame",
        "registrations.view_registration",
        "registrations.change_registration",
        "registrations.view_registrationmember",
        "registrations.view_paymentattempt",
        "registrations.change_paymentattempt",
        "registrations.view_registrationstatusevent",
    }

    def test_command_sets_only_the_v1_organizer_permissions(self):
        call_command("bootstrap_organizers")

        group = Group.objects.get(name="Organizers")
        actual_permissions = {
            f"{permission.content_type.app_label}.{permission.codename}"
            for permission in group.permissions.select_related("content_type")
        }

        self.assertSetEqual(actual_permissions, self.expected_permissions)
        self.assertNotIn("registrations.delete_registration", actual_permissions)
        self.assertNotIn("registrations.add_registration", actual_permissions)

    def test_command_is_idempotent(self):
        call_command("bootstrap_organizers")
        call_command("bootstrap_organizers")

        self.assertEqual(Group.objects.filter(name="Organizers").count(), 1)
```
- [ ] **Step 2: Run the test to confirm the command is absent**

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_management_command -v 2
```

Expected: failure because `bootstrap_organizers` is not registered.

- [ ] **Step 3: Implement the idempotent, least-privilege group bootstrap**

Create `server/registrations/management/commands/bootstrap_organizers.py`:

```python
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q


PERMISSION_SPEC = {
    "tournaments": {
        "game": ("add", "change", "view"),
        "tournament": ("add", "change", "view"),
        "tournamentgame": ("add", "change", "view"),
    },
    "registrations": {
        "registration": ("change", "view"),
        "registrationmember": ("view",),
        "paymentattempt": ("change", "view"),
        "registrationstatusevent": ("view",),
    },
}


class Command(BaseCommand):
    help = "Create or update the least-privilege Organizers group."

    def handle(self, *args, **options):
        permission_filter = Q(pk__in=[])
        required = set()
        for app_label, model_specs in PERMISSION_SPEC.items():
            for model_name, verbs in model_specs.items():
                codenames = {f"{verb}_{model_name}" for verb in verbs}
                required.update((app_label, codename) for codename in codenames)
                permission_filter |= Q(
                    content_type__app_label=app_label,
                    content_type__model=model_name,
                    codename__in=codenames,
                )

        permissions = Permission.objects.filter(permission_filter).select_related(
            "content_type"
        )
        found = {
            (permission.content_type.app_label, permission.codename)
            for permission in permissions
        }
        missing = required - found
        if missing:
            formatted = ", ".join(
                f"{app_label}.{codename}" for app_label, codename in sorted(missing)
            )
            raise CommandError(f"Required permissions are missing: {formatted}")

        group, _ = Group.objects.get_or_create(name="Organizers")
        group.permissions.set(permissions)
        self.stdout.write(self.style.SUCCESS("Organizers group is configured."))
```

The command grants no delete permission and no `add_registration` permission. Both catalog and registration Admin views require `is_staff=True`, membership in `Organizers`, and the corresponding model permission; service commands enforce the same group boundary (except for superusers).
- [ ] **Step 4: Register read-only evidence views and guarded Admin actions**

Replace `server/registrations/admin.py` with:

```python
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from .models import PaymentAttempt, Registration, RegistrationMember, RegistrationStatusEvent
from .services import (
    approve_registration,
    reject_registration,
    review_payment_attempt,
    start_review,
)


class ImmutableInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RegistrationMemberInline(ImmutableInline):
    model = RegistrationMember
    readonly_fields = (
        "user",
        "gamer_tag_snapshot",
        "school_snapshot",
        "is_captain",
        "display_order",
    )


class PaymentAttemptInline(ImmutableInline):
    model = PaymentAttempt
    readonly_fields = (
        "method",
        "status",
        "amount",
        "currency",
        "proof_file",
        "reference",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "created_at",
    )


class RegistrationStatusEventInline(ImmutableInline):
    model = RegistrationStatusEvent
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")


def _is_organizer_staff(user) -> bool:
    return user.is_authenticated and (
        user.is_superuser
        or (user.is_staff and user.groups.filter(name="Organizers").exists())
    )


class GuardedReadOnlyAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return _is_organizer_staff(request.user) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return _is_organizer_staff(request.user) and super().has_view_permission(
            request, obj
        )

    def has_change_permission(self, request, obj=None):
        return _is_organizer_staff(request.user) and super().has_change_permission(
            request, obj
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(Registration)
class RegistrationAdmin(GuardedReadOnlyAdmin):
    list_display = (
        "id",
        "tournament_game",
        "submitted_by",
        "team_name",
        "status",
        "submitted_at",
    )
    list_filter = ("status", "tournament_game__tournament", "tournament_game__game")
    search_fields = ("team_name", "submitted_by__email", "members__gamer_tag_snapshot")
    list_select_related = ("tournament_game", "submitted_by")
    inlines = (RegistrationMemberInline, PaymentAttemptInline, RegistrationStatusEventInline)
    actions = ("mark_under_review", "approve_selected", "reject_selected")

    def _run_transition(self, request, queryset, command):
        completed = 0
        for registration in queryset:
            try:
                command(actor=request.user, registration_id=registration.pk)
            except (PermissionDenied, ValidationError) as error:
                self.message_user(
                    request,
                    f"Registration {registration.pk}: {error}",
                    level=messages.ERROR,
                )
            else:
                completed += 1
        if completed:
            self.message_user(
                request,
                f"Applied transition to {completed} registration(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Mark selected registrations under review")
    def mark_under_review(self, request, queryset):
        self._run_transition(request, queryset, start_review)

    @admin.action(description="Approve selected registrations")
    def approve_selected(self, request, queryset):
        self._run_transition(request, queryset, approve_registration)

    @admin.action(description="Reject selected registrations")
    def reject_selected(self, request, queryset):
        self._run_transition(
            request,
            queryset,
            lambda *, actor, registration_id: reject_registration(
                actor=actor,
                registration_id=registration_id,
                note="Rejected by organizer.",
            ),
        )


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(GuardedReadOnlyAdmin):
    list_display = ("id", "registration", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("registration__team_name", "registration__submitted_by__email", "reference")
    list_select_related = ("registration",)
    actions = ("verify_selected", "reject_selected")

    def _review(self, request, queryset, target_status):
        completed = 0
        for payment_attempt in queryset:
            try:
                review_payment_attempt(
                    actor=request.user,
                    payment_attempt_id=payment_attempt.pk,
                    status=target_status,
                )
            except (PermissionDenied, ValidationError) as error:
                self.message_user(
                    request,
                    f"Payment attempt {payment_attempt.pk}: {error}",
                    level=messages.ERROR,
                )
            else:
                completed += 1
        if completed:
            self.message_user(
                request,
                f"Reviewed {completed} payment attempt(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Verify selected payment attempts")
    def verify_selected(self, request, queryset):
        self._review(request, queryset, PaymentAttempt.Status.VERIFIED)

    @admin.action(description="Reject selected payment attempts")
    def reject_selected(self, request, queryset):
        self._review(request, queryset, PaymentAttempt.Status.REJECTED)
```

Create `server/registrations/tests/test_admin_actions.py`:

```python
from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.utils import timezone

from registrations.admin import PaymentAttemptAdmin, RegistrationAdmin
from registrations.models import PaymentAttempt, Registration
from tournaments.admin import GameAdmin
from tournaments.models import Game, Tournament, TournamentGame


class GuardedAdminTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(
            email="organizer@example.com", password="strong-password", is_staff=True
        )
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(name="Summer", slug="summer")
        tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            team_size_min=1,
            team_size_max=1,
            registration_opens_at=timezone.now() - timedelta(minutes=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="50000.00",
            fee_currency="VND",
        )
        self.registration = Registration.objects.create(
            tournament_game=tournament_game,
            submitted_by=self.actor,
            team_name="",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot="50000.00",
            fee_currency_snapshot="VND",
        )
        self.payment_attempt = PaymentAttempt.objects.create(
            registration=self.registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            amount="50000.00",
            currency="VND",
        )
        self.request = RequestFactory().post("/admin/")
        self.request.user = self.actor

    def test_registration_admin_blocks_direct_owner_changes_and_delegates_transition(self):
        registration_admin = RegistrationAdmin(Registration, AdminSite())
        self.assertFalse(registration_admin.has_add_permission(self.request))
        self.assertFalse(
            registration_admin.has_delete_permission(self.request, self.registration)
        )
        self.assertIn(
            "submitted_by",
            registration_admin.get_readonly_fields(self.request, self.registration),
        )

        with (
            patch.object(registration_admin, "message_user"),
            patch("registrations.admin.start_review") as start_review_command,
        ):
            registration_admin.mark_under_review(
                self.request, Registration.objects.filter(pk=self.registration.pk)
            )

        start_review_command.assert_called_once_with(
            actor=self.actor, registration_id=self.registration.pk
        )

    def test_payment_admin_delegates_to_payment_service(self):
        payment_admin = PaymentAttemptAdmin(PaymentAttempt, AdminSite())

        with (
            patch.object(payment_admin, "message_user"),
            patch("registrations.admin.review_payment_attempt") as review_command,
        ):
            payment_admin.verify_selected(
                self.request, PaymentAttempt.objects.filter(pk=self.payment_attempt.pk)
            )

        review_command.assert_called_once_with(
            actor=self.actor,
            payment_attempt_id=self.payment_attempt.pk,
            status=PaymentAttempt.Status.VERIFIED,
        )
    def test_direct_model_permissions_do_not_bypass_organizer_membership(self):
        outsider = get_user_model().objects.create_user(
            email="outside-staff@example.com",
            password="strong-password",
            is_staff=True,
        )
        outsider.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="registrations", codename="view_registration"
            ),
            Permission.objects.get(
                content_type__app_label="registrations", codename="change_registration"
            ),
            Permission.objects.get(
                content_type__app_label="tournaments", codename="view_game"
            ),
            Permission.objects.get(
                content_type__app_label="tournaments", codename="change_game"
            ),
        )
        outsider_request = RequestFactory().get("/admin/")
        outsider_request.user = outsider
        registration_admin = RegistrationAdmin(Registration, AdminSite())
        game_admin = GameAdmin(Game, AdminSite())
        game = self.registration.tournament_game.game

        self.assertFalse(registration_admin.has_module_permission(outsider_request))
        self.assertFalse(
            registration_admin.has_view_permission(outsider_request, self.registration)
        )
        self.assertFalse(
            registration_admin.has_change_permission(outsider_request, self.registration)
        )
        self.assertFalse(game_admin.has_module_permission(outsider_request))
        self.assertFalse(game_admin.has_view_permission(outsider_request, game))
        self.assertFalse(game_admin.has_change_permission(outsider_request, game))
```
- [ ] **Step 5: Run organizer tests**

Run:

```powershell
cd server
uv run python manage.py test registrations.tests.test_management_command registrations.tests.test_admin_actions -v 2
```

Expected: the bootstrap command is idempotent, Admin actions delegate to the service layer, and direct staff permissions cannot bypass Organizer membership.

- [ ] **Step 6: Commit organizer operations**

```powershell
git add server/registrations/admin.py server/registrations/management server/registrations/tests
git commit -m "feat: add guarded organizer administration"
```

### Task 7: Verify migrations, system integrity, and the complete first slice

**Files:**

- None. The verified-player-claim flow is explicitly deferred by this foundation slice; any other mismatch with the approved model design requires a separate product decision. Do not silently rewrite the contract during verification.

**Interfaces:**

- Confirms every model migration is current
- Confirms all first-slice model, service, permission, API, and admin tests pass

- [ ] **Step 1: Check migration consistency**

Run:

```powershell
cd server
uv run python manage.py makemigrations --check --dry-run
```

Expected: exit `0` and `No changes detected`.

- [ ] **Step 2: Run the full Django test suite**

Run:

```powershell
cd server
uv run python manage.py test -v 2
```

Expected: all tests pass, including model constraints, services, ownership filtering, payment privacy, and admin commands.

- [ ] **Step 3: Run framework and lint checks**

Run:

```powershell
cd server
uv run python manage.py check
uv run ruff check .
```

Expected: both commands exit `0`.

- [ ] **Step 4: Review the working tree and approved contract**

Run:

```powershell
git diff --check
git diff --cached --check
git status --short
```

Confirm the implementation uses `TournamentGame`; creates immutable public player snapshots with no client-controlled player-account link; filters all participant querysets through `submitted_by`; never exposes payment proof/reference/review data in participant responses; restricts organizers to the `Organizers` group plus `is_staff`; and does not call Guardian object-permission APIs.

- [ ] **Step 5: Escalate any contract mismatch instead of changing the specification**

If a verification result conflicts with the approved design, stop implementation and present the concrete mismatch for a product decision. Do not edit `docs/superpowers/specs/2026-07-15-registration-domain-model-design.md` as part of this plan without that approval.

