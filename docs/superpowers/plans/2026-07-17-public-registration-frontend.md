# Public Registration Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the public tournament discovery, participant account/profile, registration, manual payment proof, schema/docs, and settings-hardening slice described in `docs/superpowers/specs/2026-07-17-public-registration-frontend-design.md`.

**Architecture:** Keep Django as the source of truth and expose public read APIs plus participant-auth APIs under `/api/`. Keep organizer review in Django Admin. Build SvelteKit public pages with server/universal load where no token is needed, and keep authenticated participant pages client-side for v1 because JWTs are stored in browser `localStorage`.

**Tech Stack:** Django 6.0, Django REST Framework 3.17, drf-spectacular 0.30, djangorestframework-simplejwt 5.5, PostgreSQL, SvelteKit 2.63, Svelte 5 runes mode, Paraglide, Tailwind CSS 4, Vitest, Playwright.

## Global Constraints

- Preserve the existing registration domain model; do not add brackets, stages, matches, results, standings, schedules, persistent teams, roster claims, amendments, withdrawals, payment gateways, or custom organizer frontend screens in this slice.
- Public APIs expose only published tournaments and configured game metadata.
- Participant APIs expose only the authenticated user's own account and registrations.
- Never expose public or participant payment proof file URLs, other users' payment references, review notes, organizer-only audit details, unpublished tournament details, or other users' email addresses.
- Registration submission must continue to accept roster snapshots and must not accept arbitrary `RegistrationMember.user` IDs.
- JWT remains the v1 API authentication mechanism.
- JWT storage in SvelteKit uses browser `localStorage` and is isolated behind `web/src/lib/auth/session.ts`.
- UI strings visible to users must go through Paraglide English/Vietnamese messages.
- Visual system uses Manrope headings, IBM Plex Sans body/UI, and JetBrains Mono only for mono/data.
- Visual direction uses white/neutral surfaces, Yves Klein Blue `#002FA7`, 1px hairline rules, left-aligned Swiss operations-board structure, and no neon esports styling.
- Do not use Fira Sans or Fira Mono.
- Keep Guardian installed but do not introduce Guardian object-permission usage for v1 registration ownership.
- Run backend commands from `server/` with `uv run`.
- Run frontend commands from `web/` with `pnpm`.

---

## File structure

| Path | Responsibility |
| --- | --- |
| `server/config/env.py` | Small settings helpers for booleans, comma-separated lists, and local-only secret fallback. |
| `server/config/permissions.py` | Permission class for schema/docs access: public in debug, staff-only otherwise. |
| `server/config/settings.py` | Harden env parsing, CORS origins, allowed hosts, media root, and schema settings. |
| `server/config/api_urls.py` | Mount account, tournament, registration, JWT, schema, and docs endpoints. |
| `server/config/tests/test_settings.py` | Unit tests for settings helper parsing. |
| `server/config/tests/test_schema_urls.py` | API tests for schema/docs access rules. |
| `server/accounts/serializers.py` | Account registration and current-user profile serializers. |
| `server/accounts/views.py` | Account creation and current-user retrieve/update views. |
| `server/accounts/urls.py` | Account/auth URL routes. |
| `server/accounts/tests/test_api.py` | Account registration, token, and profile API tests. |
| `server/tournaments/serializers.py` | Public tournament and tournament-game serializers. |
| `server/tournaments/views.py` | Public read-only tournament viewset. |
| `server/tournaments/urls.py` | Public tournament router. |
| `server/tournaments/tests/test_api.py` | Published/unpublished tournament API tests. |
| `server/registrations/serializers.py` | Add participant-safe payment attempt summaries and payment-required fields. |
| `server/registrations/views.py` | Prefetch safe payment attempt summaries. |
| `server/registrations/tests/test_api.py` | Update privacy expectations for safe own-payment status exposure. |
| `server/.env.example` | Document required server env names. |
| `server/README.md` | Document local setup, checks, migrations, and organizer bootstrap. |
| `web/.env.example` | Document `PUBLIC_API_BASE_URL`. |
| `web/src/lib/api/types.ts` | Shared TypeScript DTOs matching backend serializers. |
| `web/src/lib/api/client.ts` | Fetch wrapper, auth headers, JSON/form-data handling, normalized errors. |
| `web/src/lib/api/auth.ts` | Account registration, JWT, current-user profile calls. |
| `web/src/lib/api/tournaments.ts` | Published tournament list/detail calls. |
| `web/src/lib/api/registrations.ts` | Participant registration, submit, and payment calls. |
| `web/src/lib/auth/session.ts` | LocalStorage-backed JWT session helper. |
| `web/src/lib/api/client.test.ts` | Unit tests for error normalization and request headers. |
| `web/src/lib/auth/session.test.ts` | Unit tests for token save/read/clear behavior. |
| `web/src/lib/components/layout/AppShell.svelte` | Shared Swiss grid shell and navigation. |
| `web/src/lib/components/forms/Field.svelte` | Reusable accessible input field. |
| `web/src/lib/components/forms/ErrorSummary.svelte` | Form-level error summary. |
| `web/src/lib/components/tournaments/TournamentCard.svelte` | Public tournament card. |
| `web/src/lib/components/tournaments/TournamentGameRow.svelte` | Configured game row and registration window state. |
| `web/src/lib/components/registrations/RosterEditor.svelte` | Solo/team roster input UI. |
| `web/src/lib/components/registrations/StatusTimeline.svelte` | Registration status event display. |
| `web/src/lib/components/registrations/PaymentAttemptForm.svelte` | Manual proof/reference form. |
| `web/src/routes/layout.css` | Global design tokens, font families, focus states, grid utilities. |
| `web/src/routes/+layout.svelte` | Mount shell while preserving existing Paraglide locale links. |
| `web/src/routes/+page.ts` | Load published tournaments for home. |
| `web/src/routes/+page.svelte` | Home/overview page. |
| `web/src/routes/tournaments/+page.ts` | Load full tournament list. |
| `web/src/routes/tournaments/+page.svelte` | Tournament list page. |
| `web/src/routes/tournaments/[slug]/+page.ts` | Load one public tournament detail. |
| `web/src/routes/tournaments/[slug]/+page.svelte` | Tournament detail page. |
| `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.ts` | Load public tournament/game data for registration page. |
| `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte` | Auth-gated registration form. |
| `web/src/routes/auth/sign-in/+page.svelte` | Sign-in page. |
| `web/src/routes/auth/register/+page.svelte` | Account creation page. |
| `web/src/routes/account/profile/+page.ts` | Disable SSR for localStorage auth. |
| `web/src/routes/account/profile/+page.svelte` | Profile defaults page. |
| `web/src/routes/account/registrations/+page.ts` | Disable SSR for localStorage auth. |
| `web/src/routes/account/registrations/+page.svelte` | My registrations list. |
| `web/src/routes/account/registrations/[id]/+page.ts` | Disable SSR for localStorage auth. |
| `web/src/routes/account/registrations/[id]/+page.svelte` | Registration detail and payment action. |
| `web/messages/en.json` | English UI messages. |
| `web/messages/vi.json` | Vietnamese UI messages. |
| `web/src/routes/public-registration.e2e.ts` | Playwright route smoke coverage with mocked API responses. |

---

### Task 1: Harden backend settings and expose schema/docs

**Files:**

- Create: `server/config/env.py`
- Create: `server/config/permissions.py`
- Create: `server/config/tests/__init__.py`
- Create: `server/config/tests/test_settings.py`
- Create: `server/config/tests/test_schema_urls.py`
- Modify: `server/config/settings.py`
- Modify: `server/config/api_urls.py`
- Modify: `server/.env.example`
- Modify: `server/README.md`

**Interfaces:**

- Produces: `config.env.env_bool(name: str, default: bool = False) -> bool`
- Produces: `config.env.env_list(name: str, default: Iterable[str] = ()) -> list[str]`
- Produces: `config.env.local_secret_key(name: str, *, debug: bool) -> str`
- Produces: `config.permissions.DebugOrStaffSchemaPermission`
- Produces: `GET /api/schema/`
- Produces: `GET /api/docs/`

- [ ] **Step 1: Write failing settings-helper tests**

Create `server/config/tests/test_settings.py`:

```python
from django.test import SimpleTestCase

from config.env import env_bool, env_list, local_secret_key


class EnvHelperTests(SimpleTestCase):
    def test_env_list_discards_empty_values(self):
        with self.settings():
            import os

            previous = os.environ.get("EXAMPLE_LIST")
            os.environ["EXAMPLE_LIST"] = "localhost,, 127.0.0.1 ,"
            try:
                self.assertEqual(env_list("EXAMPLE_LIST"), ["localhost", "127.0.0.1"])
            finally:
                if previous is None:
                    os.environ.pop("EXAMPLE_LIST", None)
                else:
                    os.environ["EXAMPLE_LIST"] = previous

    def test_env_bool_accepts_common_true_values(self):
        import os

        previous = os.environ.get("EXAMPLE_BOOL")
        os.environ["EXAMPLE_BOOL"] = "true"
        try:
            self.assertTrue(env_bool("EXAMPLE_BOOL"))
        finally:
            if previous is None:
                os.environ.pop("EXAMPLE_BOOL", None)
            else:
                os.environ["EXAMPLE_BOOL"] = previous

    def test_secret_key_uses_local_fallback_only_in_debug(self):
        import os

        previous = os.environ.get("EMPTY_SECRET_KEY")
        os.environ.pop("EMPTY_SECRET_KEY", None)
        try:
            self.assertEqual(
                local_secret_key("EMPTY_SECRET_KEY", debug=True),
                "local-development-secret-key",
            )
            with self.assertRaises(RuntimeError):
                local_secret_key("EMPTY_SECRET_KEY", debug=False)
        finally:
            if previous is not None:
                os.environ["EMPTY_SECRET_KEY"] = previous
```

- [ ] **Step 2: Run the settings-helper test to verify it fails**

Run:

```powershell
uv run python manage.py test config.tests.test_settings -v 2
```

Expected: failure because `config.env` does not exist.

- [ ] **Step 3: Implement settings helpers**

Create `server/config/env.py`:

```python
import os
from collections.abc import Iterable


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: Iterable[str] = ()) -> list[str]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return list(default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def local_secret_key(name: str, *, debug: bool) -> str:
    raw_value = os.getenv(name, "").strip()
    if raw_value:
        return raw_value
    if debug:
        return "local-development-secret-key"
    raise RuntimeError(f"{name} must be set when DEBUG=False.")
```

- [ ] **Step 4: Replace settings env parsing**

In `server/config/settings.py`, import helpers and replace the relevant settings:

```python
from config.env import env_bool, env_list, local_secret_key
```

Use:

```python
DEBUG = env_bool("DEBUG", False)
SECRET_KEY = local_secret_key("SECRET_KEY", debug=DEBUG)

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    default=env_list("ALLOWED_HOSTS", default=("localhost", "127.0.0.1")),
)

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *env_list("CORS_ALLOWED_ORIGINS", default=env_list("CORS_ORIGINS")),
]
```

Replace the existing CORS comment with:

```python
    # Allow the local SvelteKit dev server to call the Django API during development.
```

Use:

```python
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))
```

Keep the existing DB part names:

```python
"NAME": os.getenv("DB_NAME"),
"USER": os.getenv("DB_USER"),
"PASSWORD": os.getenv("DB_PASSWORD"),
"HOST": os.getenv("DB_HOST"),
"PORT": os.getenv("DB_PORT", "5432"),
```

- [ ] **Step 5: Write failing schema/docs access tests**

Create `server/config/tests/test_schema_urls.py`:

```python
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(ROOT_URLCONF="config.urls")
class SchemaDocsAccessTests(APITestCase):
    @override_settings(DEBUG=True)
    def test_schema_and_docs_are_public_in_debug(self):
        schema_response = self.client.get("/api/schema/")
        docs_response = self.client.get("/api/docs/")

        self.assertEqual(schema_response.status_code, status.HTTP_200_OK)
        self.assertEqual(docs_response.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=False)
    def test_schema_is_staff_only_outside_debug(self):
        anonymous_response = self.client.get("/api/schema/")
        staff_user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="strong-password",
            is_staff=True,
        )

        self.client.force_authenticate(user=staff_user)
        staff_response = self.client.get("/api/schema/")

        self.assertEqual(anonymous_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(staff_response.status_code, status.HTTP_200_OK)
```

- [ ] **Step 6: Run schema/docs tests to verify they fail**

Run:

```powershell
uv run python manage.py test config.tests.test_schema_urls -v 2
```

Expected: failure because `/api/schema/` and `/api/docs/` are not mounted.

- [ ] **Step 7: Implement schema/docs permission and URLs**

Create `server/config/permissions.py`:

```python
from django.conf import settings
from rest_framework.permissions import BasePermission


class DebugOrStaffSchemaPermission(BasePermission):
    message = "API documentation is available to staff accounts."

    def has_permission(self, request, view) -> bool:
        if settings.DEBUG:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
```

Modify `server/config/api_urls.py`:

```python
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.permissions import DebugOrStaffSchemaPermission

schema_view = SpectacularAPIView.as_view(
    permission_classes=[DebugOrStaffSchemaPermission]
)

urlpatterns = [
    path("", include("registrations.urls")),
    path("schema/", schema_view, name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            permission_classes=[DebugOrStaffSchemaPermission],
        ),
        name="docs",
    ),
]
```

- [ ] **Step 8: Update server env example and README**

Replace `server/.env.example` with:

```env
TZ=Asia/Ho_Chi_Minh

DEBUG=False
SECRET_KEY=replace-this-with-a-secure-key

DB_NAME=usec_tnmt_registration
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=db
DB_PORT=5432

DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
MEDIA_ROOT=media
```

Add this section to `server/README.md`:

```markdown
## Local development

Copy `.env.example` to `.env`, then adjust database settings for your local environment.

Useful commands:

```powershell
uv run python manage.py migrate
uv run python manage.py bootstrap_organizers
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run python manage.py test -v 2
uv run ruff check .
```

API documentation is mounted at `/api/docs/`. It is public while `DEBUG=True` and staff-only while `DEBUG=False`.
```

- [ ] **Step 9: Run backend checks for this task**

Run:

```powershell
uv run python manage.py test config.tests.test_settings config.tests.test_schema_urls -v 2
uv run python manage.py check
uv run ruff check .
```

Expected: all commands exit `0`.

- [ ] **Step 10: Commit settings and schema/docs hardening**

```powershell
git add server/config server/.env.example server/README.md
git commit -m "feat: expose api schema and harden settings"
```

---

### Task 2: Add account registration, JWT routes, and current-user profile API

**Files:**

- Create: `server/accounts/serializers.py`
- Create: `server/accounts/views.py`
- Create: `server/accounts/urls.py`
- Create: `server/accounts/tests/test_api.py`
- Modify: `server/config/api_urls.py`

**Interfaces:**

- Produces: `POST /api/auth/register/`
- Produces: `POST /api/auth/token/`
- Produces: `POST /api/auth/token/refresh/`
- Produces: `GET /api/account/me/`
- Produces: `PATCH /api/account/me/`

- [ ] **Step 1: Write failing account API tests**

Create `server/accounts/tests/test_api.py`:

```python
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(ROOT_URLCONF="config.urls")
class AccountApiTests(APITestCase):
    def test_register_creates_email_login_user(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "player@example.com",
                "password": "strong-password-123",
                "gamer_tag": "usec-player",
                "school": "HCMUS",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(email="player@example.com")
        self.assertEqual(user.gamer_tag, "usec-player")
        self.assertEqual(user.school, "HCMUS")
        self.assertNotIn("password", response.data)

    def test_register_rejects_duplicate_email(self):
        get_user_model().objects.create_user(
            email="player@example.com", password="strong-password-123"
        )

        response = self.client.post(
            "/api/auth/register/",
            {"email": "player@example.com", "password": "strong-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_token_endpoint_accepts_email_password(self):
        get_user_model().objects.create_user(
            email="player@example.com", password="strong-password-123"
        )

        response = self.client.post(
            "/api/auth/token/",
            {"email": "player@example.com", "password": "strong-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_current_user_requires_authentication(self):
        response = self.client.get("/api/account/me/")

        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_current_user_read_and_patch(self):
        user = get_user_model().objects.create_user(
            email="player@example.com",
            password="strong-password-123",
            gamer_tag="old",
            school="Old School",
        )
        self.client.force_authenticate(user=user)

        get_response = self.client.get("/api/account/me/")
        patch_response = self.client.patch(
            "/api/account/me/",
            {"gamer_tag": "new", "school": "HCMUS", "email": "other@example.com"},
            format="json",
        )

        user.refresh_from_db()
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["email"], "player@example.com")
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.email, "player@example.com")
        self.assertEqual(user.gamer_tag, "new")
        self.assertEqual(user.school, "HCMUS")
```

- [ ] **Step 2: Run account API tests to verify they fail**

Run:

```powershell
uv run python manage.py test accounts.tests.test_api -v 2
```

Expected: failure because account API URLs do not exist.

- [ ] **Step 3: Implement account serializers**

Create `server/accounts/serializers.py`:

```python
from django.contrib.auth import get_user_model
from rest_framework import serializers


class AccountRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = get_user_model()
        fields = ("id", "email", "password", "gamer_tag", "school")
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop("password")
        return get_user_model().objects.create_user(password=password, **validated_data)


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "email", "gamer_tag", "school")
        read_only_fields = ("id", "email")
```

- [ ] **Step 4: Implement account views and URLs**

Create `server/accounts/views.py`:

```python
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from .serializers import AccountRegistrationSerializer, CurrentUserSerializer


class AccountRegistrationView(generics.CreateAPIView):
    serializer_class = AccountRegistrationSerializer
    permission_classes = [AllowAny]


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
```

Create `server/accounts/urls.py`:

```python
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import AccountRegistrationView, CurrentUserView

urlpatterns = [
    path("auth/register/", AccountRegistrationView.as_view(), name="account-register"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("account/me/", CurrentUserView.as_view(), name="account-me"),
]
```

Modify `server/config/api_urls.py` so `urlpatterns` includes:

```python
path("", include("accounts.urls")),
```

- [ ] **Step 5: Run account API tests**

Run:

```powershell
uv run python manage.py test accounts.tests.test_api -v 2
uv run python manage.py check
uv run ruff check .
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit account API**

```powershell
git add server/accounts server/config/api_urls.py
git commit -m "feat: add participant account api"
```

---

### Task 3: Add public tournament API

**Files:**

- Create: `server/tournaments/serializers.py`
- Create: `server/tournaments/views.py`
- Create: `server/tournaments/urls.py`
- Create: `server/tournaments/tests/test_api.py`
- Modify: `server/config/api_urls.py`

**Interfaces:**

- Produces: `GET /api/tournaments/`
- Produces: `GET /api/tournaments/{slug}/`
- Produces serializer field `tournament_games[].registration_state` with values `"not_open"`, `"open"`, `"full"`, or `"closed"`
- Produces serializer field `tournament_games[].is_registration_open: bool`

- [ ] **Step 1: Write failing public tournament API tests**

Create `server/tournaments/tests/test_api.py`:

```python
from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from registrations.models import Registration
from tournaments.models import Game, Tournament, TournamentGame


@override_settings(ROOT_URLCONF="config.urls")
class PublicTournamentApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name="Valorant", slug="valorant")
        self.published = Tournament.objects.create(
            name="USEC Summer 2026",
            slug="usec-summer-2026",
            description="Summer tournament",
            location="HCMUS",
            is_published=True,
        )
        self.unpublished = Tournament.objects.create(
            name="Draft Event",
            slug="draft-event",
            is_published=False,
        )
        self.tournament_game = TournamentGame.objects.create(
            tournament=self.published,
            game=self.game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now() - timedelta(hours=1),
            registration_closes_at=timezone.now() + timedelta(days=2),
            registration_capacity=1,
            fee_amount=Decimal("50000.00"),
            fee_currency="VND",
        )

    def test_list_returns_only_published_tournaments(self):
        response = self.client.get("/api/tournaments/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item["slug"] for item in response.data}
        self.assertEqual(slugs, {"usec-summer-2026"})

    def test_detail_returns_published_tournament_games(self):
        response = self.client.get("/api/tournaments/usec-summer-2026/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], "usec-summer-2026")
        self.assertEqual(response.data["tournament_games"][0]["game_name"], "Valorant")
        self.assertEqual(response.data["tournament_games"][0]["team_size_min"], 5)
        self.assertEqual(response.data["tournament_games"][0]["fee_currency"], "VND")
        self.assertEqual(response.data["tournament_games"][0]["registration_state"], "open")
        self.assertTrue(response.data["tournament_games"][0]["is_registration_open"])

    def test_unpublished_detail_returns_404(self):
        response = self.client.get("/api/tournaments/draft-event/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_full_game_reports_full_state(self):
        user = get_user_model().objects.create_user(
            email="player@example.com",
            password="strong-password",
        )
        Registration.objects.create(
            tournament_game=self.tournament_game,
            submitted_by=user,
            team_name="Full Team",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=Decimal("50000.00"),
            fee_currency_snapshot="VND",
        )

        response = self.client.get("/api/tournaments/usec-summer-2026/")

        self.assertEqual(
            response.data["tournament_games"][0]["registration_state"],
            "full",
        )
        self.assertFalse(response.data["tournament_games"][0]["is_registration_open"])
```

- [ ] **Step 2: Run public tournament API tests to verify they fail**

Run:

```powershell
uv run python manage.py test tournaments.tests.test_api -v 2
```

Expected: failure because public tournament URLs do not exist.

- [ ] **Step 3: Implement public tournament serializers**

Create `server/tournaments/serializers.py`:

```python
from django.utils import timezone
from rest_framework import serializers

from registrations.models import Registration

from .models import Tournament, TournamentGame


class PublicTournamentGameSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source="game.name", read_only=True)
    game_slug = serializers.CharField(source="game.slug", read_only=True)
    registration_state = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()
    capacity_remaining = serializers.SerializerMethodField()

    class Meta:
        model = TournamentGame
        fields = (
            "id",
            "game_name",
            "game_slug",
            "team_size_min",
            "team_size_max",
            "registration_opens_at",
            "registration_closes_at",
            "registration_capacity",
            "capacity_remaining",
            "fee_amount",
            "fee_currency",
            "registration_state",
            "is_registration_open",
        )

    def _active_count(self, obj: TournamentGame) -> int:
        return obj.registrations.filter(status__in=Registration.active_statuses()).count()

    def get_capacity_remaining(self, obj: TournamentGame) -> int | None:
        if obj.registration_capacity is None:
            return None
        return max(obj.registration_capacity - self._active_count(obj), 0)

    def get_registration_state(self, obj: TournamentGame) -> str:
        now = timezone.now()
        if now < obj.registration_opens_at:
            return "not_open"
        if now >= obj.registration_closes_at:
            return "closed"
        if self.get_capacity_remaining(obj) == 0:
            return "full"
        return "open"

    def get_is_registration_open(self, obj: TournamentGame) -> bool:
        return self.get_registration_state(obj) == "open"


class PublicTournamentSerializer(serializers.ModelSerializer):
    tournament_games = PublicTournamentGameSerializer(many=True, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "starts_at",
            "ends_at",
            "location",
            "tournament_games",
        )
```

- [ ] **Step 4: Implement public tournament viewset and URLs**

Create `server/tournaments/views.py`:

```python
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Tournament
from .serializers import PublicTournamentSerializer


class PublicTournamentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicTournamentSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Tournament.objects.filter(is_published=True)
            .prefetch_related("tournament_games__game", "tournament_games__registrations")
            .order_by("starts_at", "name", "pk")
        )
```

Create `server/tournaments/urls.py`:

```python
from rest_framework.routers import SimpleRouter

from .views import PublicTournamentViewSet

router = SimpleRouter()
router.register("tournaments", PublicTournamentViewSet, basename="public-tournament")

urlpatterns = router.urls
```

Modify `server/config/api_urls.py` so `urlpatterns` includes:

```python
path("", include("tournaments.urls")),
```

- [ ] **Step 5: Run public tournament API tests**

Run:

```powershell
uv run python manage.py test tournaments.tests.test_api -v 2
uv run python manage.py check
uv run ruff check .
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit public tournament API**

```powershell
git add server/tournaments server/config/api_urls.py
git commit -m "feat: add public tournament api"
```

---

### Task 4: Add participant-safe payment summaries to registration reads

**Files:**

- Modify: `server/registrations/serializers.py`
- Modify: `server/registrations/views.py`
- Modify: `server/registrations/tests/test_api.py`

**Interfaces:**

- Produces: `RegistrationReadSerializer.payment_required: bool`
- Produces: `RegistrationReadSerializer.payment_attempts[]` with only `id`, `status`, `amount`, `currency`, and `created_at`

- [ ] **Step 1: Update failing registration API privacy test**

In `server/registrations/tests/test_api.py`, update `test_owner_lists_and_retrieves_only_own_registration` so it asserts safe payment summary behavior:

```python
self.assertIn("payment_attempts", detail_response.data)
self.assertNotIn("proof_file", str(detail_response.data))
self.assertNotIn("reference", str(detail_response.data))
self.assertNotIn("review_note", str(detail_response.data))
```

Add this test:

```python
def test_registration_detail_exposes_safe_own_payment_attempt_summary(self):
    self.client.force_authenticate(user=self.owner)
    self.client.post(
        f"/api/registrations/{self.registration.pk}/payment-attempts/",
        {"amount": "50000.00", "currency": "VND", "reference": "transfer-123"},
        format="json",
    )

    response = self.client.get(f"/api/registrations/{self.registration.pk}/")

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data["payment_required"])
    self.assertEqual(len(response.data["payment_attempts"]), 1)
    self.assertEqual(response.data["payment_attempts"][0]["status"], "PENDING")
    self.assertNotIn("proof_file", response.data["payment_attempts"][0])
    self.assertNotIn("reference", response.data["payment_attempts"][0])
    self.assertNotIn("review_note", response.data["payment_attempts"][0])
```

- [ ] **Step 2: Run registration API tests to verify they fail**

Run:

```powershell
uv run python manage.py test registrations.tests.test_api -v 2
```

Expected: failure because `payment_required` and safe `payment_attempts` are not serialized.

- [ ] **Step 3: Implement safe payment attempt serializer**

In `server/registrations/serializers.py`, add:

```python
class PaymentAttemptReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAttempt
        fields = ("id", "status", "amount", "currency", "created_at")
```

Update `RegistrationReadSerializer`:

```python
payment_attempts = PaymentAttemptReadSerializer(many=True, read_only=True)
payment_required = serializers.SerializerMethodField()
```

Add `"payment_required"` and `"payment_attempts"` to `fields`.

Add this method:

```python
def get_payment_required(self, obj: Registration) -> bool:
    return obj.fee_amount_snapshot > 0
```

- [ ] **Step 4: Prefetch payment attempts in registration queryset**

In `server/registrations/views.py`, update `get_queryset()`:

```python
.prefetch_related("members", "status_events", "payment_attempts")
```

- [ ] **Step 5: Run registration API tests**

Run:

```powershell
uv run python manage.py test registrations.tests.test_api -v 2
uv run python manage.py check
uv run ruff check .
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit registration read refinement**

```powershell
git add server/registrations
git commit -m "feat: expose participant payment summaries"
```

---

### Task 5: Add frontend API types, fetch client, and session helpers

**Files:**

- Create: `web/.env.example`
- Create: `web/src/lib/api/types.ts`
- Create: `web/src/lib/api/client.ts`
- Create: `web/src/lib/api/auth.ts`
- Create: `web/src/lib/api/tournaments.ts`
- Create: `web/src/lib/api/registrations.ts`
- Create: `web/src/lib/api/client.test.ts`
- Create: `web/src/lib/auth/session.ts`
- Create: `web/src/lib/auth/session.test.ts`

**Interfaces:**

- Produces: `requestJson<T>(path: string, options?: ApiRequestOptions) -> Promise<T>`
- Produces: `saveSession(tokens: TokenPair) -> void`
- Produces: `getAccessToken() -> string | null`
- Produces: `clearSession() -> void`
- Produces: `signIn(email: string, password: string) -> Promise<TokenPair>`
- Produces: `listTournaments() -> Promise<PublicTournament[]>`
- Produces: `submitRegistration(payload: RegistrationSubmissionPayload) -> Promise<RegistrationRead>`

- [ ] **Step 1: Write failing client tests**

Create `web/src/lib/api/client.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { ApiRequestError, requestJson } from './client';

describe('requestJson', () => {
	it('adds bearer token and parses json responses', async () => {
		const fetcher = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ ok: true }), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			})
		);

		const result = await requestJson<{ ok: boolean }>('/example/', {
			accessToken: 'token',
			baseUrl: 'http://api.test',
			fetcher
		});

		expect(result.ok).toBe(true);
		const [, init] = fetcher.mock.calls[0];
		expect(fetcher).toHaveBeenCalledWith('http://api.test/example/', expect.any(Object));
		expect((init?.headers as Headers).get('authorization')).toBe('Bearer token');
	});

	it('normalizes field errors', async () => {
		const fetcher = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ email: ['This field is required.'] }), {
				status: 400,
				headers: { 'content-type': 'application/json' }
			})
		);

		await expect(
			requestJson('/example/', { baseUrl: 'http://api.test', fetcher })
		).rejects.toMatchObject<ApiRequestError>({
			status: 400,
			fieldErrors: { email: ['This field is required.'] }
		});
	});
});
```

Create `web/src/lib/auth/session.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearSession, getAccessToken, getRefreshToken, saveSession } from './session';

vi.mock('$app/environment', () => ({ browser: true }));

describe('session storage', () => {
	const store = new Map<string, string>();

	beforeEach(() => {
		store.clear();
		vi.stubGlobal('localStorage', {
			getItem: (key: string) => store.get(key) ?? null,
			setItem: (key: string, value: string) => store.set(key, value),
			removeItem: (key: string) => store.delete(key),
			clear: () => store.clear()
		});
	});

	it('saves and clears jwt tokens', () => {
		saveSession({ access: 'access-token', refresh: 'refresh-token' });

		expect(getAccessToken()).toBe('access-token');
		expect(getRefreshToken()).toBe('refresh-token');

		clearSession();

		expect(getAccessToken()).toBeNull();
		expect(getRefreshToken()).toBeNull();
	});
});
```

- [ ] **Step 2: Run frontend unit tests to verify they fail**

Run:

```powershell
pnpm test:unit -- --run
```

Expected: failure because API and session modules do not exist.

- [ ] **Step 3: Add frontend env example**

Create `web/.env.example`:

```env
PUBLIC_API_BASE_URL=http://localhost:8000/api
```

- [ ] **Step 4: Add shared API types**

Create `web/src/lib/api/types.ts`:

```ts
export type RegistrationState = 'not_open' | 'open' | 'full' | 'closed';
export type RegistrationStatus = 'SUBMITTED' | 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED';
export type PaymentAttemptStatus = 'PENDING' | 'VERIFIED' | 'REJECTED';

export interface TokenPair {
	access: string;
	refresh: string;
}

export interface CurrentUser {
	id: number;
	email: string;
	gamer_tag: string;
	school: string;
}

export interface PublicTournamentGame {
	id: number;
	game_name: string;
	game_slug: string;
	team_size_min: number;
	team_size_max: number;
	registration_opens_at: string;
	registration_closes_at: string;
	registration_capacity: number | null;
	capacity_remaining: number | null;
	fee_amount: string;
	fee_currency: string;
	registration_state: RegistrationState;
	is_registration_open: boolean;
}

export interface PublicTournament {
	id: number;
	name: string;
	slug: string;
	description: string;
	starts_at: string | null;
	ends_at: string | null;
	location: string;
	tournament_games: PublicTournamentGame[];
}

export interface RegistrationMemberInput {
	gamer_tag_snapshot: string;
	school_snapshot: string;
	is_captain: boolean;
	display_order: number;
}

export interface RegistrationSubmissionPayload {
	tournament_game: number;
	team_name: string;
	members: RegistrationMemberInput[];
}

export interface RegistrationRead {
	id: number;
	tournament_game: {
		id: number;
		tournament_name: string;
		game_name: string;
		team_size_min: number;
		team_size_max: number;
		fee_amount: string;
		fee_currency: string;
	};
	team_name: string;
	status: RegistrationStatus;
	fee_amount_snapshot: string;
	fee_currency_snapshot: string;
	submitted_at: string;
	payment_required: boolean;
	members: RegistrationMemberInput[];
	status_events: { to_status: RegistrationStatus; created_at: string }[];
	payment_attempts: {
		id: number;
		status: PaymentAttemptStatus;
		amount: string;
		currency: string;
		created_at: string;
	}[];
}
```

- [ ] **Step 5: Implement fetch client**

Create `web/src/lib/api/client.ts`:

```ts
import { PUBLIC_API_BASE_URL } from '$env/static/public';

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
	accessToken?: string | null;
	baseUrl?: string;
	body?: BodyInit | Record<string, unknown> | null;
	fetcher?: typeof fetch;
}

export class ApiRequestError extends Error {
	status: number;
	fieldErrors: Record<string, string[]>;
	nonFieldErrors: string[];
	detail?: string;

	constructor(
		status: number,
		message: string,
		fieldErrors: Record<string, string[]> = {},
		nonFieldErrors: string[] = [],
		detail?: string
	) {
		super(message);
		this.name = 'ApiRequestError';
		this.status = status;
		this.fieldErrors = fieldErrors;
		this.nonFieldErrors = nonFieldErrors;
		this.detail = detail;
	}
}

function normalizeErrors(status: number, payload: unknown): ApiRequestError {
	if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
		const fieldErrors: Record<string, string[]> = {};
		let detail: string | undefined;
		const nonFieldErrors: string[] = [];

		for (const [key, value] of Object.entries(payload)) {
			const values = Array.isArray(value) ? value.map(String) : [String(value)];
			if (key === 'detail') detail = values[0];
			else if (key === 'non_field_errors') nonFieldErrors.push(...values);
			else fieldErrors[key] = values;
		}

		return new ApiRequestError(
			status,
			detail ?? nonFieldErrors[0] ?? 'Request failed.',
			fieldErrors,
			nonFieldErrors,
			detail
		);
	}

	return new ApiRequestError(status, 'Request failed.');
}

export async function requestJson<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
	const {
		accessToken,
		baseUrl = PUBLIC_API_BASE_URL,
		body,
		fetcher = fetch,
		headers,
		...init
	} = options;
	const requestHeaders = new Headers(headers);

	let requestBody: BodyInit | undefined;
	if (body instanceof FormData) {
		requestBody = body;
	} else if (body != null) {
		requestHeaders.set('content-type', 'application/json');
		requestBody = JSON.stringify(body);
	}

	if (accessToken) requestHeaders.set('authorization', `Bearer ${accessToken}`);

	const response = await fetcher(`${baseUrl}${path}`, {
		...init,
		body: requestBody,
		headers: requestHeaders
	});

	if (response.status === 204) return undefined as T;

	const payload = await response.json().catch(() => null);
	if (!response.ok) throw normalizeErrors(response.status, payload);
	return payload as T;
}
```

- [ ] **Step 6: Implement session and endpoint wrappers**

Create `web/src/lib/auth/session.ts`:

```ts
import { browser } from '$app/environment';
import type { TokenPair } from '$lib/api/types';

const ACCESS_TOKEN_KEY = 'usec.accessToken';
const REFRESH_TOKEN_KEY = 'usec.refreshToken';

export function saveSession(tokens: TokenPair): void {
	if (!browser) return;
	localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
	localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
}

export function getAccessToken(): string | null {
	if (!browser) return null;
	return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
	if (!browser) return null;
	return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function clearSession(): void {
	if (!browser) return;
	localStorage.removeItem(ACCESS_TOKEN_KEY);
	localStorage.removeItem(REFRESH_TOKEN_KEY);
}
```

Create wrappers in `web/src/lib/api/auth.ts`, `web/src/lib/api/tournaments.ts`, and `web/src/lib/api/registrations.ts` using `requestJson`. Use these exact function names:

```ts
// auth.ts
import { requestJson } from './client';
import type { CurrentUser, TokenPair } from './types';

export function registerAccount(payload: {
	email: string;
	password: string;
	gamer_tag?: string;
	school?: string;
}) {
	return requestJson<CurrentUser>('/auth/register/', { method: 'POST', body: payload });
}

export function signIn(email: string, password: string) {
	return requestJson<TokenPair>('/auth/token/', { method: 'POST', body: { email, password } });
}

export function getCurrentUser(accessToken: string) {
	return requestJson<CurrentUser>('/account/me/', { accessToken });
}

export function updateCurrentUser(
	accessToken: string,
	payload: Pick<CurrentUser, 'gamer_tag' | 'school'>
) {
	return requestJson<CurrentUser>('/account/me/', {
		method: 'PATCH',
		accessToken,
		body: payload
	});
}
```

```ts
// tournaments.ts
import { requestJson } from './client';
import type { PublicTournament } from './types';

export function listTournaments() {
	return requestJson<PublicTournament[]>('/tournaments/');
}

export function getTournament(slug: string) {
	return requestJson<PublicTournament>(`/tournaments/${slug}/`);
}
```

```ts
// registrations.ts
import { requestJson } from './client';
import type { RegistrationRead, RegistrationSubmissionPayload } from './types';

export function listRegistrations(accessToken: string) {
	return requestJson<RegistrationRead[]>('/registrations/', { accessToken });
}

export function getRegistration(accessToken: string, id: number) {
	return requestJson<RegistrationRead>(`/registrations/${id}/`, { accessToken });
}

export function submitRegistration(accessToken: string, payload: RegistrationSubmissionPayload) {
	return requestJson<RegistrationRead>('/registrations/submit/', {
		method: 'POST',
		accessToken,
		body: payload
	});
}

export function submitPaymentAttempt(accessToken: string, registrationId: number, formData: FormData) {
	return requestJson<RegistrationRead['payment_attempts'][number]>(
		`/registrations/${registrationId}/payment-attempts/`,
		{ method: 'POST', accessToken, body: formData }
	);
}
```

- [ ] **Step 7: Run frontend API tests**

Run:

```powershell
pnpm test:unit -- --run
pnpm check
```

Expected: both commands exit `0`.

- [ ] **Step 8: Commit frontend API foundation**

```powershell
git add web/.env.example web/src/lib/api web/src/lib/auth
git commit -m "feat: add frontend api client"
```

---

### Task 6: Add frontend visual system, shell, and reusable components

**Files:**

- Modify: `web/src/routes/layout.css`
- Modify: `web/src/routes/+layout.svelte`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`
- Create: `web/src/lib/components/layout/AppShell.svelte`
- Create: `web/src/lib/components/forms/Field.svelte`
- Create: `web/src/lib/components/forms/ErrorSummary.svelte`
- Create: `web/src/lib/components/tournaments/TournamentCard.svelte`
- Create: `web/src/lib/components/tournaments/TournamentGameRow.svelte`
- Create: `web/src/lib/components/registrations/StatusTimeline.svelte`

**Interfaces:**

- Produces: `<AppShell>{children}</AppShell>`
- Produces: `<Field label name value error type>`
- Produces: `<ErrorSummary errors>`
- Produces: `<TournamentCard tournament>`
- Produces: `<TournamentGameRow tournament game>`
- Produces: `<StatusTimeline events>`

- [ ] **Step 1: Replace message files with base UI copy**

Replace `web/messages/en.json` with keys for navigation, empty states, actions, forms, status labels, and tournament labels. Include at least:

```json
{
	"$schema": "https://inlang.com/schema/inlang-message-format",
	"app_title": "USEC Tournament Registration Hub",
	"nav_tournaments": "Tournaments",
	"nav_my_registrations": "My registrations",
	"nav_profile": "Profile",
	"nav_sign_in": "Sign in",
	"action_create_account": "Create account",
	"action_register": "Register",
	"action_save_profile": "Save profile",
	"action_upload_payment_proof": "Upload payment proof",
	"empty_tournaments": "No published tournaments are available.",
	"empty_registrations": "You have not submitted a registration yet.",
	"field_email": "Email",
	"field_password": "Password",
	"field_gamer_tag": "Gamer tag",
	"field_school": "School",
	"field_team_name": "Team name",
	"status_SUBMITTED": "Submitted",
	"status_UNDER_REVIEW": "Under review",
	"status_APPROVED": "Approved",
	"status_REJECTED": "Rejected",
	"registration_state_not_open": "Not open",
	"registration_state_open": "Open",
	"registration_state_full": "Full",
	"registration_state_closed": "Closed"
}
```

Replace `web/messages/vi.json` with equivalent Vietnamese strings using the same keys.

- [ ] **Step 2: Implement global CSS tokens**

Replace `web/src/routes/layout.css` with:

```css
@import 'tailwindcss';
@plugin '@tailwindcss/forms';

:root {
	font-family: 'IBM Plex Sans', system-ui, sans-serif;
	color: #111827;
	background: #ffffff;
	--surface: #ffffff;
	--surface-muted: #f7f7f8;
	--text: #111827;
	--text-muted: #5b6472;
	--line: #d9dee7;
	--accent: #002fa7;
	--warning: #b45309;
	--error: #b91c1c;
	--success: #047857;
}

html {
	background: var(--surface);
}

body {
	margin: 0;
	min-width: 320px;
	background: var(--surface);
	color: var(--text);
}

h1,
h2,
h3,
.font-heading {
	font-family: Manrope, 'IBM Plex Sans', system-ui, sans-serif;
	letter-spacing: -0.03em;
}

.font-mono-data {
	font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Consolas, monospace;
	font-variant-numeric: tabular-nums;
}

a {
	color: inherit;
	text-decoration-color: var(--line);
	text-underline-offset: 0.18em;
}

a:hover {
	color: var(--accent);
	text-decoration-color: var(--accent);
}

:focus-visible {
	outline: 2px solid var(--accent);
	outline-offset: 3px;
}

.grid-board {
	border: 1px solid var(--line);
	background:
		linear-gradient(var(--line) 1px, transparent 1px),
		linear-gradient(90deg, var(--line) 1px, transparent 1px);
	background-size: 100% 4rem, 16rem 100%;
}
```

- [ ] **Step 3: Implement AppShell**

Create `web/src/lib/components/layout/AppShell.svelte`:

```svelte
<script lang="ts">
	import * as m from '$lib/paraglide/messages';

	let { children } = $props();
</script>

<div class="min-h-screen bg-white text-[var(--text)]">
	<header class="border-b border-[var(--line)]">
		<nav class="mx-auto grid max-w-6xl grid-cols-1 gap-px md:grid-cols-[1fr_auto]">
			<a class="font-heading px-4 py-4 text-xl font-semibold" href="/">{m.app_title()}</a>
			<div class="flex flex-wrap border-t border-[var(--line)] md:border-l md:border-t-0">
				<a class="px-4 py-4 text-sm" href="/tournaments">{m.nav_tournaments()}</a>
				<a class="px-4 py-4 text-sm" href="/account/registrations">{m.nav_my_registrations()}</a>
				<a class="px-4 py-4 text-sm" href="/account/profile">{m.nav_profile()}</a>
				<a class="px-4 py-4 text-sm" href="/auth/sign-in">{m.nav_sign_in()}</a>
			</div>
		</nav>
	</header>

	<main class="mx-auto max-w-6xl px-4 py-8">
		{@render children()}
	</main>
</div>
```

- [ ] **Step 4: Mount AppShell in root layout**

Modify `web/src/routes/+layout.svelte`:

```svelte
<script lang="ts">
	import type { Pathname } from '$app/types';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { locales, localizeHref } from '$lib/paraglide/runtime';
	import AppShell from '$lib/components/layout/AppShell.svelte';
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<AppShell>
	{@render children()}
</AppShell>

<div style="display:none">
	{#each locales as locale (locale)}
		<a href={resolve(localizeHref(page.url.pathname, { locale }) as Pathname)}>{locale}</a>
	{/each}
</div>
```

- [ ] **Step 5: Implement reusable display/form components**

Create the component files listed in this task. Keep the props explicit and typed. `TournamentCard` and `TournamentGameRow` consume types from `$lib/api/types`. `Field` renders a real `<label>` and `aria-describedby` when an error exists. `ErrorSummary` renders nothing when `errors.length === 0`. `StatusTimeline` uses `font-mono-data` for dates only.

- [ ] **Step 6: Run frontend checks**

Run:

```powershell
pnpm check
pnpm lint
```

Expected: both commands exit `0`.

- [ ] **Step 7: Commit frontend shell and components**

```powershell
git add web/src/routes web/src/lib/components web/messages
git commit -m "feat: add frontend design system"
```

---

### Task 7: Build public tournament pages

**Files:**

- Create: `web/src/routes/+page.ts`
- Modify: `web/src/routes/+page.svelte`
- Create: `web/src/routes/tournaments/+page.ts`
- Create: `web/src/routes/tournaments/+page.svelte`
- Create: `web/src/routes/tournaments/[slug]/+page.ts`
- Create: `web/src/routes/tournaments/[slug]/+page.svelte`

**Interfaces:**

- Consumes: `listTournaments()`
- Consumes: `getTournament(slug: string)`
- Produces: public home, tournament list, and tournament detail pages.

- [ ] **Step 1: Add home page load**

Create `web/src/routes/+page.ts`:

```ts
import { listTournaments } from '$lib/api/tournaments';

export async function load() {
	return {
		tournaments: await listTournaments()
	};
}
```

- [ ] **Step 2: Replace starter home page**

Replace `web/src/routes/+page.svelte` with a page that:

- sets `<title>USEC Tournament Registration Hub</title>`;
- renders `m.app_title()`;
- renders real tournaments from `data.tournaments`;
- renders `m.empty_tournaments()` when the list is empty;
- uses `<TournamentCard>` for each tournament.

Use this script block:

```svelte
<script lang="ts">
	import TournamentCard from '$lib/components/tournaments/TournamentCard.svelte';
	import * as m from '$lib/paraglide/messages';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>
```

- [ ] **Step 3: Add tournament list page**

Create `web/src/routes/tournaments/+page.ts`:

```ts
import { listTournaments } from '$lib/api/tournaments';

export async function load() {
	return {
		tournaments: await listTournaments()
	};
}
```

Create `web/src/routes/tournaments/+page.svelte` using the same `TournamentCard` list and empty state as the home page, with a more direct heading: "Published tournaments" via a Paraglide message key.

- [ ] **Step 4: Add tournament detail page**

Create `web/src/routes/tournaments/[slug]/+page.ts`:

```ts
import { error } from '@sveltejs/kit';
import { ApiRequestError } from '$lib/api/client';
import { getTournament } from '$lib/api/tournaments';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => {
	try {
		return {
			tournament: await getTournament(params.slug)
		};
	} catch (cause) {
		if (cause instanceof ApiRequestError && cause.status === 404) {
			error(404, 'Tournament not found');
		}
		throw cause;
	}
};
```

Create `web/src/routes/tournaments/[slug]/+page.svelte` that renders:

- tournament name, description, starts/ends/location;
- a game list using `<TournamentGameRow tournament={data.tournament} game={game} />`;
- a standard `Register` link only when `game.is_registration_open` is true.

- [ ] **Step 5: Add route smoke tests with mocked API**

Create `web/src/routes/public-registration.e2e.ts`:

```ts
import { expect, test } from '@playwright/test';

test('home renders published tournaments from api', async ({ page }) => {
	await page.route('**/api/tournaments/', async (route) => {
		await route.fulfill({
			json: [
				{
					id: 1,
					name: 'USEC Summer 2026',
					slug: 'usec-summer-2026',
					description: 'Summer tournament',
					starts_at: null,
					ends_at: null,
					location: 'HCMUS',
					tournament_games: []
				}
			]
		});
	});

	await page.goto('/');

	await expect(page.getByRole('heading', { name: 'USEC Tournament Registration Hub' })).toBeVisible();
	await expect(page.getByText('USEC Summer 2026')).toBeVisible();
});
```

- [ ] **Step 6: Run frontend checks**

Run:

```powershell
pnpm check
pnpm lint
```

Expected: both commands exit `0`.

- [ ] **Step 7: Commit public tournament pages**

```powershell
git add web/src/routes web/messages
git commit -m "feat: add public tournament pages"
```

---

### Task 8: Build auth and profile pages

**Files:**

- Create: `web/src/routes/auth/sign-in/+page.svelte`
- Create: `web/src/routes/auth/register/+page.svelte`
- Create: `web/src/routes/account/profile/+page.ts`
- Create: `web/src/routes/account/profile/+page.svelte`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**

- Consumes: `signIn(email, password)`
- Consumes: `registerAccount(payload)`
- Consumes: `getCurrentUser(accessToken)`
- Consumes: `updateCurrentUser(accessToken, payload)`
- Consumes: `saveSession(tokens)` and `getAccessToken()`

- [ ] **Step 1: Implement sign-in page**

Create `web/src/routes/auth/sign-in/+page.svelte`. It should:

- render email and password fields;
- call `signIn(email, password)`;
- call `saveSession(tokens)`;
- redirect with `goto(redirectTo || '/account/registrations')`;
- show `ApiRequestError` field/form errors.

Use standard button copy `m.nav_sign_in()`.

- [ ] **Step 2: Implement account creation page**

Create `web/src/routes/auth/register/+page.svelte`. It should:

- render email, password, gamer tag, and school fields;
- call `registerAccount`;
- call `signIn` immediately after successful account creation;
- save tokens and redirect to `/account/profile`;
- show field/form errors.

- [ ] **Step 3: Disable SSR for profile page**

Create `web/src/routes/account/profile/+page.ts`:

```ts
export const ssr = false;
```

- [ ] **Step 4: Implement profile page**

Create `web/src/routes/account/profile/+page.svelte`. It should:

- on mount, redirect unauthenticated users to `/auth/sign-in?redirectTo=/account/profile`;
- load current user with `getCurrentUser(accessToken)`;
- render gamer tag and school fields;
- submit with `updateCurrentUser`;
- never allow email editing.

- [ ] **Step 5: Add auth/profile Playwright coverage**

Extend `web/src/routes/public-registration.e2e.ts` with a mocked sign-in redirect test:

```ts
test('profile redirects unauthenticated visitors to sign in', async ({ page }) => {
	await page.goto('/account/profile');
	await expect(page).toHaveURL(/\/auth\/sign-in/);
});
```

- [ ] **Step 6: Run frontend checks**

Run:

```powershell
pnpm check
pnpm lint
```

Expected: both commands exit `0`.

- [ ] **Step 7: Commit auth and profile pages**

```powershell
git add web/src/routes/auth web/src/routes/account/profile web/messages
git commit -m "feat: add participant auth pages"
```

---

### Task 9: Build registration form and participant registration pages

**Files:**

- Create: `web/src/lib/components/registrations/RosterEditor.svelte`
- Create: `web/src/lib/components/registrations/PaymentAttemptForm.svelte`
- Create: `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.ts`
- Create: `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- Create: `web/src/routes/account/registrations/+page.ts`
- Create: `web/src/routes/account/registrations/+page.svelte`
- Create: `web/src/routes/account/registrations/[id]/+page.ts`
- Create: `web/src/routes/account/registrations/[id]/+page.svelte`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**

- Consumes: `getTournament(slug)`
- Consumes: `getCurrentUser(accessToken)`
- Consumes: `submitRegistration(accessToken, payload)`
- Consumes: `listRegistrations(accessToken)`
- Consumes: `getRegistration(accessToken, id)`
- Consumes: `submitPaymentAttempt(accessToken, registrationId, formData)`

- [ ] **Step 1: Implement `RosterEditor.svelte`**

Create `web/src/lib/components/registrations/RosterEditor.svelte`. It accepts:

```ts
interface Props {
	teamSizeMin: number;
	teamSizeMax: number;
	initialGamerTag: string;
	initialSchool: string;
}
```

It produces a local `members` array of `RegistrationMemberInput`. It must:

- render exactly one row for solo games;
- render `teamSizeMax` rows for fixed-size team games;
- mark the first row as captain by default;
- let users move captain status to one row only;
- require gamer tag and school fields.

- [ ] **Step 2: Add registration page load**

Create `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.ts`:

```ts
import { error } from '@sveltejs/kit';
import { getTournament } from '$lib/api/tournaments';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => {
	const tournament = await getTournament(params.slug);
	const game = tournament.tournament_games.find((item) => item.id === Number(params.gameId));
	if (!game) error(404, 'Tournament game not found');
	return { tournament, game };
};
```

- [ ] **Step 3: Implement registration page**

Create `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`. It should:

- redirect unauthenticated users to `/auth/sign-in?redirectTo=<current path>`;
- load current user and prefill first roster row;
- render team name only when `data.game.team_size_max > 1`;
- submit `RegistrationSubmissionPayload`;
- redirect to `/account/registrations/{id}` on success.

- [ ] **Step 4: Add account registrations list page**

Create `web/src/routes/account/registrations/+page.ts`:

```ts
export const ssr = false;
```

Create `web/src/routes/account/registrations/+page.svelte`. It should:

- redirect unauthenticated users to sign in;
- call `listRegistrations(accessToken)`;
- render empty state `m.empty_registrations()`;
- link each registration to `/account/registrations/{id}`;
- show status, tournament name, game name, submitted date, and fee snapshot.

- [ ] **Step 5: Add registration detail and payment form**

Create `web/src/routes/account/registrations/[id]/+page.ts`:

```ts
export const ssr = false;
```

Create `web/src/routes/account/registrations/[id]/+page.svelte`. It should:

- redirect unauthenticated users to sign in;
- call `getRegistration(accessToken, Number(params.id))`;
- render roster snapshots;
- render status timeline using `<StatusTimeline>`;
- render `<PaymentAttemptForm>` only when `registration.payment_required` is true;
- refresh the registration detail after successful payment proof upload.

Create `web/src/lib/components/registrations/PaymentAttemptForm.svelte` with amount, currency, proof file, and reference fields. Use `FormData` so file upload works.

- [ ] **Step 6: Add registration route smoke tests**

Extend `web/src/routes/public-registration.e2e.ts`:

```ts
test('register page redirects unauthenticated visitors to sign in', async ({ page }) => {
	await page.route('**/api/tournaments/usec-summer-2026/', async (route) => {
		await route.fulfill({
			json: {
				id: 1,
				name: 'USEC Summer 2026',
				slug: 'usec-summer-2026',
				description: '',
				starts_at: null,
				ends_at: null,
				location: 'HCMUS',
				tournament_games: [
					{
						id: 10,
						game_name: 'Valorant',
						game_slug: 'valorant',
						team_size_min: 5,
						team_size_max: 5,
						registration_opens_at: '2026-07-01T00:00:00Z',
						registration_closes_at: '2026-07-31T00:00:00Z',
						registration_capacity: 16,
						capacity_remaining: 16,
						fee_amount: '50000.00',
						fee_currency: 'VND',
						registration_state: 'open',
						is_registration_open: true
					}
				]
			}
		});
	});

	await page.goto('/tournaments/usec-summer-2026/games/10/register');
	await expect(page).toHaveURL(/\/auth\/sign-in/);
});
```

- [ ] **Step 7: Run frontend checks**

Run:

```powershell
pnpm check
pnpm lint
pnpm test:unit -- --run
```

Expected: all commands exit `0`.

- [ ] **Step 8: Commit participant registration pages**

```powershell
git add web/src/lib/components/registrations web/src/routes web/messages
git commit -m "feat: add participant registration flow"
```

---

### Task 10: Final integration verification

**Files:**

- None unless verification exposes a concrete defect.

**Interfaces:**

- Confirms all backend and frontend checks for the full slice.

- [ ] **Step 1: Check migration consistency**

Run from `server/`:

```powershell
uv run python manage.py makemigrations --check --dry-run
```

Expected: exit `0` and no model changes detected.

- [ ] **Step 2: Run full backend verification**

Run from `server/`:

```powershell
uv run python manage.py check
uv run python manage.py test -v 2
uv run ruff check .
```

Expected: all commands exit `0`.

- [ ] **Step 3: Run full frontend verification**

Run from `web/`:

```powershell
pnpm check
pnpm lint
pnpm test:unit -- --run
pnpm test:e2e
```

Expected: all commands exit `0`.

- [ ] **Step 4: Verify schema includes new endpoints**

Run from `server/`:

```powershell
uv run python manage.py spectacular --file schema.yml
```

Expected: generated schema includes `/api/tournaments/`, `/api/tournaments/{slug}/`, `/api/auth/register/`, `/api/auth/token/`, `/api/auth/token/refresh/`, `/api/account/me/`, `/api/registrations/`, `/api/registrations/submit/`, and `/api/registrations/{id}/payment-attempts/`.

Remove `server/schema.yml` after inspection if it is not intentionally tracked.

- [ ] **Step 5: Review working tree**

Run:

```powershell
git status --short
```

Expected: only intentional implementation files are changed. Existing unrelated untracked files remain untouched unless the user explicitly asks to handle them.

- [ ] **Step 6: Commit verification fixes if needed**

If verification required fixes, commit only those fixes:

```powershell
git add <fixed-files>
git commit -m "fix: stabilize public registration flow"
```

If verification did not require fixes, do not create an empty commit.

