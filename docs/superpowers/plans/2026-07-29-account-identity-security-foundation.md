# Account Identity Security Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 1 by making account/session behavior predictable, completing the institution catalogue, and protecting public self-service forms with Turnstile plus deployment-rate-limit guidance.

**Architecture:** The backend owns institution identity, Turnstile verification, and endpoint permission checks. The frontend owns visible logout, reusable institution and Turnstile components, protected-form token collection, and predictable auth-state UX. Production rate limiting is documented as Cloudflare WAF plus NGINX origin controls and remains a deployment task after domains are final.

**Tech Stack:** Django 6, Django REST Framework, SimpleJWT, Python `unittest`, urllib stdlib HTTPS calls, SvelteKit 2, Svelte 5, TypeScript, Paraglide, Vitest browser mode, Playwright, pnpm, uv

## Global Constraints

- Expose logout clearly in the authenticated application shell.
- Make login, logout, expired sessions, redirects, and protected pages behave consistently for participants and organizers.
- Replace account-level free-text `school` with the shared institution catalogue described in `2026-07-22-account-institution-design.md`.
- Keep account identity separate from tournament-specific roles. Captain, manager, roster member, entrant, and result behavior remain registration or competition data, not persistent account roles.
- Guard every public self-service form with Cloudflare Turnstile: account registration, sign-in, tournament registration submission, and manual payment proof submission.
- Keep Turnstile secrets out of browser code.
- Allow local development to continue when Turnstile keys are missing, with clear developer warnings.
- Fail loudly outside development if required Turnstile environment variables are missing.
- Document Cloudflare WAF and NGINX rate limiting as the production defense layer after domains and hosting are final.
- Do not build a frontend organizer/admin panel.
- Do not implement Redis or application-level distributed rate limiting in this phase.
- Do not create Cloudflare WAF rules, Worker rate-limit bindings, DNS records, or NGINX production config before deployment domains are chosen.
- Do not add account-wide tournament-specific roles.
- Do not change the registration captain/manager model before the registration-flow phase.
- Do not implement SePay, brackets, Channels, TFT, Round Robin, or Swiss.

---

## Planned File Structure

| Path | Responsibility |
| --- | --- |
| `docs/superpowers/plans/2026-07-22-account-institution-catalogue.md` | Existing detailed implementation plan for the institution catalogue slice. |
| `server/accounts/models.py` | Institution model, user institution relation, private staff reference data. |
| `server/accounts/services/institutions.py` | Institution label normalization and catalogue/custom resolution. |
| `server/accounts/management/commands/import_institutions.py` | Idempotent import of `server/university.json`. |
| `server/accounts/serializers.py` | Account registration/profile serializers and institution search responses. |
| `server/accounts/views.py` | Account registration, current user, institution search, and Turnstile-protected sign-in view. |
| `server/accounts/urls.py` | Account, auth, token, and institution search routes. |
| `server/config/turnstile.py` | Server-only Turnstile settings, dev bypass, and Siteverify service. |
| `server/config/checks.py` | Django system checks for production Turnstile secrets. |
| `server/config/settings.py` | Turnstile settings import and production configuration. |
| `server/registrations/serializers.py` | `turnstile_token` fields on protected registration/payment submissions. |
| `server/registrations/views.py` | Turnstile verification before registration/payment mutations. |
| `server/.env.example` | Backend Turnstile variable documentation. |
| `web/scripts/check-turnstile-env.mjs` | Production build check for `PUBLIC_TURNSTILE_SITE_KEY`. |
| `web/src/lib/turnstile/config.ts` | Public site-key lookup and dev/build enforcement helpers. |
| `web/src/lib/components/forms/TurnstileWidget.svelte` | Reusable client Turnstile widget with dev passthrough warning. |
| `web/src/lib/api/auth.ts` | Turnstile token payloads for sign-in and account registration. |
| `web/src/lib/api/registrations.ts` | Turnstile token payloads for registration and payment proof APIs. |
| `web/src/routes/auth/sign-in/+page.svelte` | Turnstile-protected sign-in form. |
| `web/src/routes/auth/register/+page.svelte` | Institution and Turnstile-protected account registration form. |
| `web/src/routes/auth/logout/+page.svelte` | Visible client logout route if retained. |
| `web/src/routes/account/profile/+page.svelte` | Institution profile editing. |
| `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte` | Turnstile-protected tournament registration submission. |
| `web/src/routes/account/registrations/[id]/+page.svelte` | Manual payment proof Turnstile insertion when the payment form is present. |
| `web/src/lib/components/layout/AppShell.svelte` | Signed-in navigation with logout action. |
| `web/messages/en.json` and `web/messages/vi.json` | Logout, institution, Turnstile, and rate-limit/admin-facing text. |
| `docs/deployment/security-rate-limits.md` | Cloudflare WAF and NGINX production rate-limit guidance. |
| `docs/TODO.md` | Phase 1 checklist updates only after verified completion. |

### Task 1: Make Logout Visible and Auth Redirects Consistent

**Files:**
- Modify: `web/src/lib/components/layout/AppShell.svelte`
- Modify: `web/src/lib/components/layout/AppShell.svelte.spec.ts`
- Modify: `web/src/lib/states/auth-state.svelte.ts`
- Modify: `web/src/lib/states/auth-state.test.ts`
- Create or replace: `web/src/routes/auth/logout/+page.svelte`
- Modify: `web/src/routes/auth-pages.svelte.spec.ts`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**
- Consumes: `authState.signOut(): void`
- Produces: `authState.signOutAndRedirect(targetHref?: string): void`
- Produces: signed-in shell link `href={resolve(localizeInternalHref('/auth/logout'))}`

- [ ] **Step 1: Write failing auth-state logout redirect tests**

Add these cases to `web/src/lib/states/auth-state.test.ts`:

```typescript
it('clears the session and redirects on explicit sign-out', () => {
	const state = new AuthState();
	saveSession(tokens);

	state.signOutAndRedirect('/signed-out');

	expect(getAccessToken()).toBeNull();
	expect(getRefreshToken()).toBeNull();
	expect(replaceInternalLocation).toHaveBeenCalledWith('/signed-out');
	expect(state.status).toBe('signed-out');
	expect(state.currentUser).toBeNull();
});

it('uses the localized home route when explicit sign-out has no target', () => {
	const state = new AuthState();

	state.signOutAndRedirect();

	expect(replaceInternalLocation).toHaveBeenCalledWith('/');
});
```

- [ ] **Step 2: Run auth-state tests and verify the red state**

Run from `web/`:

```powershell
pnpm exec vitest run src/lib/states/auth-state.test.ts
```

Expected: FAIL because `signOutAndRedirect` is not defined.

- [ ] **Step 3: Implement the logout redirect helper**

Add this public method to `AuthState` in `web/src/lib/states/auth-state.svelte.ts`:

```typescript
signOutAndRedirect(targetHref = resolve(localizeInternalHref('/'))): void {
	this.signOut();
	replaceInternalLocation(targetHref);
}
```

Keep the existing `signOut()` method as the non-navigation primitive used by auth expiry handling.

- [ ] **Step 4: Run auth-state tests and verify green**

Run from `web/`:

```powershell
pnpm exec vitest run src/lib/states/auth-state.test.ts
```

Expected: PASS.

- [ ] **Step 5: Write failing shell/logout route tests**

In `web/src/lib/components/layout/AppShell.svelte.spec.ts`, add:

```typescript
it('shows a logout link for signed-in users', async () => {
	authStateMock.status = 'signed-in';
	authStateMock.currentUser = user;
	authStateMock.initialize.mockResolvedValue(user);

	renderShell();

	await expect.element(page.getByRole('link', { name: m.nav_logout() })).toBeVisible();
	expect(page.getByRole('link', { name: m.nav_logout() })).toHaveAttribute('href', '/auth/logout');
});
```

In `web/src/routes/auth-pages.svelte.spec.ts`, add a logout page section:

```typescript
it('signs out and redirects to the localized home page', async () => {
	authStateMock.signOutAndRedirect.mockClear();
	render(LogoutPage);

	await vi.waitFor(() => expect(authStateMock.signOutAndRedirect).toHaveBeenCalledWith('/'));
	await expect.element(page.getByText(m.auth_signed_out_redirecting())).toBeVisible();
});
```

Extend the auth-state route mock with:

```typescript
signOutAndRedirect: vi.fn()
```

- [ ] **Step 6: Run shell and auth-page tests and verify red**

Run from `web/`:

```powershell
pnpm exec vitest run src/lib/components/layout/AppShell.svelte.spec.ts src/routes/auth-pages.svelte.spec.ts
```

Expected: FAIL because `nav_logout`, `auth_signed_out_redirecting`, and the logout UI are missing.

- [ ] **Step 7: Add logout UI and messages**

Add messages:

```json
"nav_logout": "Log out",
"auth_signed_out_redirecting": "You are signed out. Returning to the homepage..."
```

Vietnamese:

```json
"nav_logout": "Đăng xuất",
"auth_signed_out_redirecting": "Bạn đã đăng xuất. Đang quay về trang chủ..."
```

Add this signed-in shell link after `nav_my_registrations` in `AppShell.svelte`:

```svelte
<a
	class="flex items-center border-(--line) px-4 py-2 text-sm font-medium"
	href={resolve(localizeInternalHref('/auth/logout'))}
>
	{m.nav_logout()}
</a>
```

Replace `web/src/routes/auth/logout/+page.svelte` with:

```svelte
<script lang="ts">
	import { resolve } from '$app/paths';
	import { authState } from '$lib/states/auth-state.svelte';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { onMount } from 'svelte';

	onMount(() => {
		authState.signOutAndRedirect(resolve(localizeInternalHref('/')));
	});
</script>

<svelte:head>
	<title>{m.nav_logout()} · {m.app_title()}</title>
</svelte:head>

<p class="mt-8 border border-(--line) bg-(--surface-muted) p-6 text-sm" role="status">
	{m.auth_signed_out_redirecting()}
</p>
```

- [ ] **Step 8: Verify logout UI**

Run from `web/`:

```powershell
pnpm exec vitest run src/lib/states/auth-state.test.ts src/lib/components/layout/AppShell.svelte.spec.ts src/routes/auth-pages.svelte.spec.ts
```

Expected: PASS.

- [ ] **Step 9: Commit logout slice**

```powershell
git add web/src/lib/states/auth-state.svelte.ts web/src/lib/states/auth-state.test.ts web/src/lib/components/layout/AppShell.svelte web/src/lib/components/layout/AppShell.svelte.spec.ts web/src/routes/auth/logout/+page.svelte web/src/routes/auth-pages.svelte.spec.ts web/messages/en.json web/messages/vi.json
git commit -m "feat: expose account logout"
```

### Task 2: Execute the Institution Catalogue Backend Slice

**Files:**
- Follow: `docs/superpowers/plans/2026-07-22-account-institution-catalogue.md`
- Create: `server/accounts/services/__init__.py`
- Create: `server/accounts/services/institutions.py`
- Create: `server/accounts/management/__init__.py`
- Create: `server/accounts/management/commands/__init__.py`
- Create: `server/accounts/management/commands/import_institutions.py`
- Create: `server/accounts/migrations/0003_institution_catalogue.py`
- Create: `server/accounts/tests/test_institutions.py`
- Modify: `server/accounts/models.py`
- Modify: `server/accounts/managers.py`
- Modify: `server/accounts/admin.py`
- Modify: `server/accounts/serializers.py`
- Modify: `server/accounts/views.py`
- Modify: `server/accounts/urls.py`
- Modify: `server/accounts/tests/test_api.py`
- Modify: `server/accounts/tests/test_models.py`
- Modify: `server/README.md`

**Interfaces:**
- Produces: `Institution`
- Produces: `normalize_institution_label(value: str) -> str`
- Produces: `resolve_institution(*, institution_id: int | None, institution_label: str | None) -> Institution`
- Produces: `GET /api/institutions/?q=<text>`
- Produces: account response `institution: { id, value, label, code, shortName, eng, type, location } | null`
- Produces: account write inputs `institution_id` or `institution_label`

- [ ] **Step 1: Execute July 22 plan Task 1 exactly**

Open `docs/superpowers/plans/2026-07-22-account-institution-catalogue.md` and complete Task 1 from that plan:

```powershell
uv run python manage.py test accounts.tests.test_institutions -v 2
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test accounts.tests.test_institutions accounts.tests.test_models -v 2
```

Expected red/green behavior is the one written in the July 22 plan: the first focused tests fail before `Institution` exists, then pass after the model, migration, service, and admin changes are implemented.

- [ ] **Step 2: Execute July 22 plan Task 2 exactly**

Complete the import command task and verify:

```powershell
uv run python manage.py test accounts.tests.test_institutions.InstitutionImportCommandTests -v 2
uv run python manage.py import_institutions
```

Expected: tests PASS and the command reports created/updated catalogue records from `server/university.json`.

- [ ] **Step 3: Execute July 22 plan Task 3 exactly**

Complete the institution search and account API task and verify:

```powershell
uv run python manage.py test accounts.tests.test_api accounts.tests.test_institutions -v 2
uv run python manage.py check
```

Expected: PASS and `System check identified no issues (0 silenced).`

- [ ] **Step 4: Confirm no account API exposes staff-only fields**

Add or keep this assertion in `server/accounts/tests/test_api.py`:

```python
self.assertNotIn("student_id", response.data)
self.assertNotIn("source", response.data["institution"])
self.assertNotIn("review_status", response.data["institution"])
self.assertNotIn("normalized_label", response.data["institution"])
```

Run:

```powershell
uv run python manage.py test accounts.tests.test_api -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit backend institution slice**

```powershell
git add server/accounts server/README.md
git commit -m "feat: add institution account backend"
```

### Task 3: Execute the Institution Catalogue Frontend Slice

**Files:**
- Follow: `docs/superpowers/plans/2026-07-22-account-institution-catalogue.md`
- Create: `web/src/lib/api/institutions.ts`
- Create: `web/src/lib/components/forms/InstitutionCombobox.svelte`
- Create: `web/src/lib/components/forms/institution-combobox.svelte.spec.ts`
- Modify: `web/src/lib/api/types.ts`
- Modify: `web/src/lib/api/auth.ts`
- Modify: `web/src/routes/auth/register/+page.svelte`
- Modify: `web/src/routes/account/profile/+page.svelte`
- Modify: `web/src/routes/auth-pages.svelte.spec.ts`
- Modify: `web/src/routes/registration-pages.svelte.spec.ts`
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**
- Consumes: `GET /api/institutions/?q=<text>`
- Produces: `Institution`
- Produces: `InstitutionChoice`
- Produces: `searchInstitutions(query: string): Promise<Institution[]>`
- Produces: `<InstitutionCombobox bind:choice />`

- [ ] **Step 1: Execute July 22 plan Task 4 exactly**

Complete the institution API and combobox task. Verify:

```powershell
pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts
pnpm check
```

Expected: the combobox test fails before the component exists, then passes after the API module and component are implemented. `pnpm check` has no institution-related diagnostics.

- [ ] **Step 2: Execute July 22 plan Task 5 exactly, except preserve Phase 1 Turnstile edits for later tasks**

Update account registration and profile pages to use `<InstitutionCombobox>`, and update account fixtures to use `CurrentUser.institution`. Do not wire Turnstile in this task; Task 5 of this Phase 1 plan owns Turnstile form wiring.

Run:

```powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts
pnpm check
```

Expected: PASS for account institution behavior and roster snapshot independence.

- [ ] **Step 3: Execute July 22 plan Task 6 exactly**

Repair backend fixtures impacted by required names/institution data. Verify:

```powershell
uv run python manage.py test accounts config registrations tournaments -v 2
uv run ruff check .
```

Expected: account-manager fixture failures are gone and ruff passes.

- [ ] **Step 4: Commit frontend institution slice**

```powershell
git add web/src/lib/api web/src/lib/components/forms web/src/routes web/src/lib/components/registrations web/messages server/accounts/tests server/config/tests server/registrations/tests server/tournaments/tests
git commit -m "feat: use institutions in account settings"
```

### Task 4: Add Backend Turnstile Verification and Production Checks

**Files:**
- Create: `server/config/turnstile.py`
- Create: `server/config/checks.py`
- Modify: `server/config/apps.py` if the project app config needs explicit check import
- Modify: `server/config/settings.py`
- Modify: `server/config/tests/test_settings.py`
- Create: `server/config/tests/test_turnstile.py`
- Modify: `server/accounts/serializers.py`
- Modify: `server/accounts/views.py`
- Modify: `server/accounts/urls.py`
- Modify: `server/accounts/tests/test_api.py`
- Modify: `server/registrations/serializers.py`
- Modify: `server/registrations/views.py`
- Modify: `server/registrations/tests/test_api.py`
- Modify: `server/.env.example`

**Interfaces:**
- Produces: `TurnstileVerificationResult`
- Produces: `verify_turnstile_token(token: str, *, expected_action: str, remote_ip: str | None = None) -> TurnstileVerificationResult`
- Produces: `TurnstileProtectedTokenObtainPairView`
- Consumes: `settings.DEBUG`, `settings.TURNSTILE_SECRET_KEY`, `settings.TURNSTILE_SITEVERIFY_URL`
- Consumes request field: `turnstile_token`

- [ ] **Step 1: Write failing Turnstile service tests**

Create `server/config/tests/test_turnstile.py`:

```python
from django.test import TestCase, override_settings

from config.turnstile import verify_turnstile_token


class TurnstileVerificationTests(TestCase):
    @override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
    def test_debug_without_secret_bypasses_verification(self):
        result = verify_turnstile_token(
            "",
            expected_action="sign-in",
            remote_ip="127.0.0.1",
        )

        self.assertTrue(result.success)
        self.assertTrue(result.bypassed)
        self.assertEqual(result.error_codes, ("missing-secret-debug-bypass",))

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_production_without_secret_rejects(self):
        result = verify_turnstile_token(
            "token",
            expected_action="sign-in",
            remote_ip="203.0.113.10",
        )

        self.assertFalse(result.success)
        self.assertFalse(result.bypassed)
        self.assertEqual(result.error_codes, ("missing-secret",))
```

- [ ] **Step 2: Run service tests and verify red**

Run from `server/`:

```powershell
uv run python manage.py test config.tests.test_turnstile -v 2
```

Expected: FAIL because `config.turnstile` does not exist.

- [ ] **Step 3: Add Turnstile settings**

In `server/config/settings.py`, add:

```python
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_SITEVERIFY_URL = os.getenv(
    "TURNSTILE_SITEVERIFY_URL",
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
)
```

In `server/.env.example`, add:

```env
TURNSTILE_SECRET_KEY=
TURNSTILE_SITEVERIFY_URL=https://challenges.cloudflare.com/turnstile/v0/siteverify
```

- [ ] **Step 4: Implement the Turnstile service**

Create `server/config/turnstile.py`:

```python
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class TurnstileVerificationResult:
    success: bool
    bypassed: bool = False
    error_codes: tuple[str, ...] = ()


def verify_turnstile_token(
    token: str,
    *,
    expected_action: str,
    remote_ip: str | None = None,
) -> TurnstileVerificationResult:
    secret = settings.TURNSTILE_SECRET_KEY
    if not secret:
        if settings.DEBUG:
            return TurnstileVerificationResult(
                success=True,
                bypassed=True,
                error_codes=("missing-secret-debug-bypass",),
            )
        return TurnstileVerificationResult(success=False, error_codes=("missing-secret",))

    if not token:
        return TurnstileVerificationResult(success=False, error_codes=("missing-input-response",))

    payload = {
        "secret": secret,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        settings.TURNSTILE_SITEVERIFY_URL,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return TurnstileVerificationResult(success=False, error_codes=("siteverify-unavailable",))

    error_codes = tuple(data.get("error-codes", ()))
    if not data.get("success"):
        return TurnstileVerificationResult(success=False, error_codes=error_codes)

    action = data.get("action")
    if action and action != expected_action:
        return TurnstileVerificationResult(success=False, error_codes=("action-mismatch",))

    return TurnstileVerificationResult(success=True)
```

- [ ] **Step 5: Verify initial service behavior**

Run:

```powershell
uv run python manage.py test config.tests.test_turnstile -v 2
```

Expected: PASS.

- [ ] **Step 6: Add tests for Siteverify success, failure, duplicate, and action mismatch**

Add to `server/config/tests/test_turnstile.py`:

```python
from unittest.mock import patch
from io import BytesIO


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="secret")
def test_siteverify_success_accepts_matching_action(self):
    with patch("config.turnstile.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _Response(b'{"success": true, "action": "sign-in"}')

        result = verify_turnstile_token("token", expected_action="sign-in")

    self.assertTrue(result.success)
    self.assertFalse(result.bypassed)


@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="secret")
def test_siteverify_timeout_or_duplicate_rejects_with_retry_code(self):
    with patch("config.turnstile.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _Response(
            b'{"success": false, "error-codes": ["timeout-or-duplicate"]}'
        )

        result = verify_turnstile_token("token", expected_action="sign-in")

    self.assertFalse(result.success)
    self.assertEqual(result.error_codes, ("timeout-or-duplicate",))


@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="secret")
def test_siteverify_action_mismatch_rejects(self):
    with patch("config.turnstile.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _Response(b'{"success": true, "action": "account-register"}')

        result = verify_turnstile_token("token", expected_action="sign-in")

    self.assertFalse(result.success)
    self.assertEqual(result.error_codes, ("action-mismatch",))
```

If these functions are added inside the existing class, include `self` as the first argument.

- [ ] **Step 7: Run expanded service tests and verify green**

Run:

```powershell
uv run python manage.py test config.tests.test_turnstile -v 2
```

Expected: PASS.

- [ ] **Step 8: Add production system check tests**

In `server/config/tests/test_settings.py`, add:

```python
from django.core.checks import Error
from django.test import override_settings

from config.checks import check_turnstile_settings


@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
def test_turnstile_secret_is_required_outside_debug(self):
    messages = check_turnstile_settings(app_configs=None)

    self.assertEqual(len(messages), 1)
    self.assertIsInstance(messages[0], Error)
    self.assertEqual(messages[0].id, "config.E001")


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
def test_turnstile_secret_can_be_missing_in_debug(self):
    self.assertEqual(check_turnstile_settings(app_configs=None), [])
```

- [ ] **Step 9: Run system check tests and verify red**

Run:

```powershell
uv run python manage.py test config.tests.test_settings -v 2
```

Expected: FAIL because `config.checks` does not exist.

- [ ] **Step 10: Implement the system check**

Create `server/config/checks.py`:

```python
from django.conf import settings
from django.core.checks import Error, register


@register()
def check_turnstile_settings(app_configs, **kwargs):
    if settings.DEBUG or settings.TURNSTILE_SECRET_KEY:
        return []
    return [
        Error(
            "TURNSTILE_SECRET_KEY must be set when DEBUG=False.",
            id="config.E001",
        )
    ]
```

If `config` has an `AppConfig`, import `config.checks` in its `ready()` method. If it does not, add a short test that `python manage.py check` emits `config.E001` when `DEBUG=False` and the key is absent before relying on automatic registration.

- [ ] **Step 11: Verify system checks**

Run:

```powershell
uv run python manage.py test config.tests.test_settings -v 2
uv run python manage.py check
```

Expected: PASS in the current development env with configured or debug-safe settings.

- [ ] **Step 12: Write failing protected endpoint tests**

In `server/accounts/tests/test_api.py`, add:

```python
@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
def test_register_requires_turnstile_outside_debug(self):
    response = self.client.post(
        "/api/auth/register/",
        {
            "email": "player@example.com",
            "password": "strong-password-123",
            "first_name": "Minh",
            "last_name": "Nguyen",
            "institution_label": "University of Science",
        },
        format="json",
    )

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("turnstile_token", response.data)


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
def test_register_allows_debug_bypass_when_secret_missing(self):
    response = self.client.post(
        "/api/auth/register/",
        {
            "email": "player@example.com",
            "password": "strong-password-123",
            "first_name": "Minh",
            "last_name": "Nguyen",
            "institution_label": "University of Science",
        },
        format="json",
    )

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
```

Add sign-in tests:

```python
@ignore_warnings(category=InsecureKeyLengthWarning)
@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
def test_token_endpoint_requires_turnstile_outside_debug(self):
    create_account(email="player@example.com", password="strong-password-123")

    response = self.client.post(
        "/api/auth/token/",
        {"email": "player@example.com", "password": "strong-password-123"},
        format="json",
    )

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("turnstile_token", response.data)
```

In `server/registrations/tests/test_api.py`, add:

```python
@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
def test_submit_requires_turnstile_outside_debug(self):
    self.client.force_authenticate(user=self.user)

    response = self.client.post(self.submit_url, self.valid_payload, format="json")

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("turnstile_token", response.data)
```

Add a payment-attempt version using the existing valid registration fixture:

```python
@override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
def test_payment_attempt_requires_turnstile_outside_debug(self):
    self.client.force_authenticate(user=self.user)

    response = self.client.post(
        f"/api/registrations/{self.registration.pk}/payment-attempts/",
        {"amount": "50000.00", "currency": "VND", "reference": "BANK123"},
        format="json",
    )

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("turnstile_token", response.data)
```

Adapt fixture names to the existing test class setup if `self.submit_url`, `self.valid_payload`, or `self.registration` use different names.

- [ ] **Step 13: Run endpoint tests and verify red**

Run:

```powershell
uv run python manage.py test accounts.tests.test_api registrations.tests.test_api -v 2
```

Expected: FAIL because views do not call Turnstile verification and serializers reject unknown `turnstile_token`.

- [ ] **Step 14: Add serializer fields and protected view calls**

In `server/accounts/serializers.py`, add a write-only field to `AccountRegistrationSerializer`:

```python
turnstile_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
```

Remove it before user creation:

```python
validated_data.pop("turnstile_token", None)
```

In `server/registrations/serializers.py`, add:

```python
turnstile_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
```

to both `RegistrationSubmissionSerializer` and `PaymentAttemptSubmissionSerializer`.

Add a small view helper in both `server/accounts/views.py` and `server/registrations/views.py` or place it in `server/config/turnstile.py`:

```python
from rest_framework.exceptions import ValidationError as DRFValidationError


def require_turnstile(request, *, token: str, expected_action: str) -> None:
    result = verify_turnstile_token(
        token,
        expected_action=expected_action,
        remote_ip=request.META.get("REMOTE_ADDR"),
    )
    if not result.success:
        raise DRFValidationError({"turnstile_token": list(result.error_codes) or ["invalid"]})
```

In `AccountRegistrationView.perform_create`, verify before save:

```python
def perform_create(self, serializer):
    require_turnstile(
        self.request,
        token=serializer.validated_data.get("turnstile_token", ""),
        expected_action="account-register",
    )
    serializer.save()
```

Create `TurnstileProtectedTokenObtainPairView` in `server/accounts/views.py`:

```python
from rest_framework_simplejwt.views import TokenObtainPairView


class TurnstileProtectedTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        require_turnstile(
            request,
            token=request.data.get("turnstile_token", ""),
            expected_action="sign-in",
        )
        return super().post(request, *args, **kwargs)
```

Update `server/accounts/urls.py` to use the protected view:

```python
path("auth/token/", TurnstileProtectedTokenObtainPairView.as_view(), name="token-obtain-pair")
```

In `RegistrationViewSet.submit`, call before `submit_registration`:

```python
require_turnstile(
    request,
    token=serializer.validated_data.get("turnstile_token", ""),
    expected_action="registration-submit",
)
```

In `RegistrationViewSet.payment_attempts`, call before `submit_payment_attempt`:

```python
require_turnstile(
    request,
    token=serializer.validated_data.get("turnstile_token", ""),
    expected_action="payment-proof-submit",
)
```

- [ ] **Step 15: Verify backend Turnstile endpoint behavior**

Run:

```powershell
uv run python manage.py test config.tests.test_turnstile accounts.tests.test_api registrations.tests.test_api -v 2
uv run python manage.py check
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 16: Commit backend Turnstile slice**

```powershell
git add server/config server/accounts server/registrations server/.env.example
git commit -m "feat: verify turnstile on public actions"
```

### Task 5: Add Frontend Turnstile Config, Component, and API Contracts

**Files:**
- Create: `web/scripts/check-turnstile-env.mjs`
- Create: `web/src/lib/turnstile/config.ts`
- Create: `web/src/lib/components/forms/TurnstileWidget.svelte`
- Create: `web/src/lib/components/forms/turnstile-widget.svelte.spec.ts`
- Modify: `web/src/lib/api/auth.ts`
- Modify: `web/src/lib/api/auth.test.ts`
- Modify: `web/src/lib/api/registrations.ts`
- Modify: `web/src/lib/api/types.ts`
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`
- Modify: `web/package.json`
- Modify: `web/.env.example`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**
- Produces: `getTurnstileSiteKey(): string`
- Produces: `hasTurnstileSiteKey(): boolean`
- Produces: `type TurnstileAction = 'sign-in' | 'account-register' | 'registration-submit' | 'payment-proof-submit'`
- Produces: `<TurnstileWidget action="sign-in" bind:token />`
- Produces protected payload field `turnstile_token`

- [ ] **Step 1: Write failing env-check script test by direct command**

Create `web/scripts/check-turnstile-env.mjs` as a failing placeholder is not allowed, so write the test expectation first in prose and run the missing script:

```powershell
node ./scripts/check-turnstile-env.mjs
```

Expected: FAIL with `Cannot find module` because the script does not exist.

- [ ] **Step 2: Implement production build env check**

Create `web/scripts/check-turnstile-env.mjs`:

```javascript
const siteKey = process.env.PUBLIC_TURNSTILE_SITE_KEY?.trim();

if (!siteKey) {
	console.error('PUBLIC_TURNSTILE_SITE_KEY is required for production builds.');
	process.exit(1);
}
```

Modify `web/package.json`:

```json
"build": "node ./scripts/check-turnstile-env.mjs && vite build"
```

Add to `web/.env.example`:

```env
PUBLIC_TURNSTILE_SITE_KEY=
```

- [ ] **Step 3: Verify env-check script behavior**

Run from `web/`:

```powershell
$env:PUBLIC_TURNSTILE_SITE_KEY='1x00000000000000000000AA'; node ./scripts/check-turnstile-env.mjs
```

Expected: exit 0.

Run:

```powershell
Remove-Item Env:\PUBLIC_TURNSTILE_SITE_KEY -ErrorAction SilentlyContinue; node ./scripts/check-turnstile-env.mjs
```

Expected: exit 1 and `PUBLIC_TURNSTILE_SITE_KEY is required for production builds.`

- [ ] **Step 4: Write failing Turnstile component tests**

Create `web/src/lib/components/forms/turnstile-widget.svelte.spec.ts`:

```typescript
import { render } from 'vitest-browser-svelte';
import { expect, it, vi, beforeEach } from 'vitest';
import { page } from '@vitest/browser/context';
import TurnstileWidget from './TurnstileWidget.svelte';

vi.mock('$app/environment', () => ({ dev: true, browser: true }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

beforeEach(() => {
	document.body.innerHTML = '';
});

it('renders a development warning when the site key is missing', async () => {
	render(TurnstileWidget, { action: 'sign-in', token: '' });

	await expect.element(page.getByText(/PUBLIC_TURNSTILE_SITE_KEY/)).toBeVisible();
});
```

- [ ] **Step 5: Run component test and verify red**

Run:

```powershell
pnpm exec vitest run src/lib/components/forms/turnstile-widget.svelte.spec.ts
```

Expected: FAIL because `TurnstileWidget.svelte` does not exist.

- [ ] **Step 6: Add public config helper and component**

Create `web/src/lib/turnstile/config.ts`:

```typescript
import { dev } from '$app/environment';
import { env } from '$env/dynamic/public';

export type TurnstileAction =
	| 'sign-in'
	| 'account-register'
	| 'registration-submit'
	| 'payment-proof-submit';

export function getTurnstileSiteKey(): string {
	const siteKey = env.PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? '';
	if (!siteKey && !dev) {
		throw new Error('PUBLIC_TURNSTILE_SITE_KEY is required outside development.');
	}
	return siteKey;
}

export function hasTurnstileSiteKey(): boolean {
	return getTurnstileSiteKey().length > 0;
}
```

Create `web/src/lib/components/forms/TurnstileWidget.svelte`:

```svelte
<script lang="ts">
	import { browser } from '$app/environment';
	import { getTurnstileSiteKey, type TurnstileAction } from '$lib/turnstile/config';
	import * as m from '$lib/paraglide/messages';
	import { onMount } from 'svelte';

	interface Props {
		action: TurnstileAction;
		token: string;
	}

	let { action, token = $bindable('') }: Props = $props();
	let container: HTMLDivElement | null = $state(null);
	let siteKey = $state('');
	let warning = $state('');

	onMount(() => {
		siteKey = getTurnstileSiteKey();
		if (!siteKey) {
			warning = m.turnstile_dev_missing_key();
			return;
		}
		if (!browser || !container) return;

		const existing = document.querySelector<HTMLScriptElement>('script[data-turnstile-api]');
		const script =
			existing ??
			Object.assign(document.createElement('script'), {
				src: 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit',
				async: true,
				defer: true,
				dataset: { turnstileApi: 'true' }
			});
		if (!existing) document.head.appendChild(script);

		script.addEventListener(
			'load',
			() => {
				window.turnstile?.render(container, {
					sitekey: siteKey,
					action,
					callback: (value: string) => {
						token = value;
					},
					'expired-callback': () => {
						token = '';
					},
					'error-callback': () => {
						token = '';
					}
				});
			},
			{ once: true }
		);
	});
</script>

<div class="grid gap-2">
	<div bind:this={container} data-turnstile-action={action}></div>
	{#if warning}
		<p class="text-xs text-warning" role="status">{warning}</p>
	{/if}
</div>
```

Add this global type to `web/src/app.d.ts`:

```typescript
declare global {
	interface Window {
		turnstile?: {
			render: (
				container: HTMLElement,
				options: {
					sitekey: string;
					action: string;
					callback: (token: string) => void;
					'expired-callback': () => void;
					'error-callback': () => void;
				}
			) => string;
		};
	}
}
```

Add messages:

```json
"turnstile_dev_missing_key": "Development bypass: set PUBLIC_TURNSTILE_SITE_KEY in web/.env to render Cloudflare Turnstile.",
"turnstile_required": "Complete the security check before submitting."
```

Vietnamese:

```json
"turnstile_dev_missing_key": "Bỏ qua trong môi trường phát triển: đặt PUBLIC_TURNSTILE_SITE_KEY trong web/.env để hiển thị Cloudflare Turnstile.",
"turnstile_required": "Hoàn tất bước kiểm tra bảo mật trước khi gửi."
```

- [ ] **Step 7: Verify component**

Run:

```powershell
pnpm exec vitest run src/lib/components/forms/turnstile-widget.svelte.spec.ts
pnpm check
```

Expected: PASS.

- [ ] **Step 8: Write failing API contract tests**

In `web/src/lib/api/auth.test.ts`, add:

```typescript
it('sends turnstile token during sign in', async () => {
	fetchMock.mockResolvedValueOnce(jsonResponse({ access: 'access', refresh: 'refresh' }));

	await signIn('player@example.com', 'strong-password', 'turnstile-token');

	expect(fetchMock).toHaveBeenCalledWith(
		'/api/auth/token/',
		expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({
				email: 'player@example.com',
				password: 'strong-password',
				turnstile_token: 'turnstile-token'
			})
		})
	);
});
```

Add registration API tests in the same style for `registerAccount`.

In `web/src/lib/api/registrations.test.ts`, create or extend tests:

```typescript
it('sends turnstile token during registration submission', async () => {
	fetchMock.mockResolvedValueOnce(jsonResponse(registration));

	await submitRegistration('access', payload, 'turnstile-token');

	expect(fetchMock).toHaveBeenCalledWith(
		'/api/registrations/submit/',
		expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({ ...payload, turnstile_token: 'turnstile-token' })
		})
	);
});
```

- [ ] **Step 9: Run API tests and verify red**

Run:

```powershell
pnpm exec vitest run src/lib/api/auth.test.ts src/lib/api/registrations.test.ts
```

Expected: FAIL because API functions do not accept or send Turnstile tokens.

- [ ] **Step 10: Update API contracts**

In `web/src/lib/api/auth.ts`:

```typescript
export function registerAccount(payload: RegisterAccountPayload, turnstileToken: string) {
	return requestJson<CurrentUser>('/auth/register/', {
		method: 'POST',
		body: { ...payload, turnstile_token: turnstileToken }
	});
}

export function signIn(email: string, password: string, turnstileToken: string) {
	return requestJson<TokenPair>('/auth/token/', {
		method: 'POST',
		body: { email, password, turnstile_token: turnstileToken }
	});
}
```

Define `RegisterAccountPayload` in `web/src/lib/api/types.ts` after institution migration:

```typescript
export type RegisterAccountPayload = {
	email: string;
	password: string;
	first_name: string;
	last_name: string;
} & InstitutionChoice;
```

In `web/src/lib/api/registrations.ts`:

```typescript
export function submitRegistration(
	accessToken: string,
	payload: RegistrationSubmissionPayload,
	turnstileToken: string
) {
	return requestJson<RegistrationRead>('/registrations/submit/', {
		method: 'POST',
		accessToken,
		body: { ...payload, turnstile_token: turnstileToken }
	});
}

export function submitPaymentAttempt(
	accessToken: string,
	registrationId: number,
	formData: FormData,
	turnstileToken: string
) {
	formData.set('turnstile_token', turnstileToken);
	return requestJson<RegistrationRead['payment_attempts'][number]>(
		`/registrations/${registrationId}/payment-attempts/`,
		{ method: 'POST', accessToken, body: formData }
	);
}
```

- [ ] **Step 11: Verify API contracts**

Run:

```powershell
pnpm exec vitest run src/lib/api/auth.test.ts src/lib/api/registrations.test.ts
pnpm check
```

Expected: PASS.

- [ ] **Step 12: Commit frontend Turnstile primitive**

```powershell
git add web/scripts web/package.json web/.env.example web/src/lib/turnstile web/src/lib/components/forms/TurnstileWidget.svelte web/src/lib/components/forms/turnstile-widget.svelte.spec.ts web/src/lib/api web/src/app.d.ts web/messages
git commit -m "feat: add turnstile frontend primitive"
```

### Task 6: Wire Turnstile Into Public Self-Service Forms

**Files:**
- Modify: `web/src/routes/auth/sign-in/+page.svelte`
- Modify: `web/src/routes/auth/register/+page.svelte`
- Modify: `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- Modify: `web/src/routes/account/registrations/[id]/+page.svelte`
- Modify: `web/src/routes/auth-pages.svelte.spec.ts`
- Modify: `web/src/routes/registration-pages.svelte.spec.ts`
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**
- Consumes: `<TurnstileWidget action bind:token />`
- Consumes: `signIn(email, password, turnstileToken)`
- Consumes: `registerAccount(payload, turnstileToken)`
- Consumes: `submitRegistration(accessToken, payload, turnstileToken)`
- Consumes: `submitPaymentAttempt(accessToken, registrationId, formData, turnstileToken)`

- [ ] **Step 1: Write failing sign-in and registration form tests**

In `web/src/routes/auth-pages.svelte.spec.ts`, mock `TurnstileWidget` with a component that writes a token through bindable state or sets token via a test button. Add tests:

```typescript
it('blocks sign-in until Turnstile has a token', async () => {
	render(SignInPage);

	await page.getByLabelText('Email').fill('player@example.com');
	await page.getByLabelText('Password').fill('strong-password');
	await page.getByRole('button', { name: 'Sign in' }).click();

	await expect.element(page.getByText(m.turnstile_required())).toBeVisible();
	expect(authStateMock.signIn).not.toHaveBeenCalled();
});

it('passes the Turnstile token to sign-in', async () => {
	authStateMock.signIn.mockResolvedValue(user);
	render(SignInPage);

	setMockTurnstileToken('sign-in-token');
	await page.getByLabelText('Email').fill('player@example.com');
	await page.getByLabelText('Password').fill('strong-password');
	await page.getByRole('button', { name: 'Sign in' }).click();

	await vi.waitFor(() =>
		expect(authStateMock.signIn).toHaveBeenCalledWith(
			'player@example.com',
			'strong-password',
			'sign-in-token'
		)
	);
});
```

Add account registration coverage:

```typescript
expect(registerAccount).toHaveBeenCalledWith(
	expect.objectContaining({ email: 'player@example.com' }),
	'account-register-token'
);
```

- [ ] **Step 2: Run auth page tests and verify red**

Run:

```powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts
```

Expected: FAIL because pages do not render Turnstile or pass tokens.

- [ ] **Step 3: Wire sign-in form**

In `web/src/routes/auth/sign-in/+page.svelte`, import:

```typescript
import TurnstileWidget from '$lib/components/forms/TurnstileWidget.svelte';
```

Add state:

```typescript
let turnstileToken = $state('');
```

At the start of submit after duplicate-submit guard:

```typescript
if (!turnstileToken) {
	formErrors = [m.turnstile_required()];
	return;
}
```

Call:

```typescript
const user = await authState.signIn(email, password, turnstileToken);
```

Render before footer:

```svelte
<TurnstileWidget action="sign-in" bind:token={turnstileToken} />
```

Update `AuthState.signIn` to accept and pass the token:

```typescript
async signIn(email: string, password: string, turnstileToken: string): Promise<CurrentUser | null> {
	const tokens = await requestSignIn(email, password, turnstileToken).catch(...)
}
```

- [ ] **Step 4: Wire account registration form**

In `web/src/routes/auth/register/+page.svelte`, import `TurnstileWidget`, add:

```typescript
let turnstileToken = $state('');
```

Before calling `registerAccount`:

```typescript
if (!turnstileToken) {
	formErrors = [m.turnstile_required()];
	submitting = false;
	return;
}
```

Call:

```typescript
const account = await registerAccount(
	{
		email,
		password,
		first_name: firstName,
		last_name: lastName,
		...institutionChoice
	},
	turnstileToken
);
```

Render:

```svelte
<TurnstileWidget action="account-register" bind:token={turnstileToken} />
```

- [ ] **Step 5: Verify auth form wiring**

Run:

```powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/lib/states/auth-state.test.ts
```

Expected: PASS.

- [ ] **Step 6: Write failing tournament registration Turnstile tests**

In `web/src/routes/registration-pages.svelte.spec.ts`, add:

```typescript
it('requires Turnstile before submitting tournament registration', async () => {
	render(RegistrationPage, { data: registrationPageData });

	await fillValidRoster(page);
	await page.getByRole('button', { name: m.action_submit_registration() }).click();

	await expect.element(page.getByText(m.turnstile_required())).toBeVisible();
	expect(submitRegistration).not.toHaveBeenCalled();
});

it('passes Turnstile token to tournament registration submission', async () => {
	vi.mocked(submitRegistration).mockResolvedValue(registration);
	render(RegistrationPage, { data: registrationPageData });

	setMockTurnstileToken('registration-submit-token');
	await fillValidRoster(page);
	await page.getByRole('button', { name: m.action_submit_registration() }).click();

	await vi.waitFor(() =>
		expect(submitRegistration).toHaveBeenCalledWith(
			tokens.access,
			expect.any(Object),
			'registration-submit-token'
		)
	);
});
```

- [ ] **Step 7: Run registration page tests and verify red**

Run:

```powershell
pnpm exec vitest run src/routes/registration-pages.svelte.spec.ts
```

Expected: FAIL because registration page does not render Turnstile or pass tokens.

- [ ] **Step 8: Wire tournament registration form**

In `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`, import `TurnstileWidget`, add:

```typescript
let turnstileToken = $state('');
```

Before submit:

```typescript
if (!turnstileToken) {
	formErrors = [m.turnstile_required()];
	return;
}
```

Call:

```typescript
const registration = await submitRegistration(
	accessToken,
	{
		tournament_game: data.game.id,
		team_name: data.game.team_size_max > 1 ? teamName : '',
		members
	},
	turnstileToken
);
```

Render near the form footer:

```svelte
<TurnstileWidget action="registration-submit" bind:token={turnstileToken} />
```

- [ ] **Step 9: Wire payment proof when the payment form exists**

Search the detail page for `submitPaymentAttempt`. If the form exists in `web/src/routes/account/registrations/[id]/+page.svelte`, add:

```svelte
<TurnstileWidget action="payment-proof-submit" bind:token={turnstileToken} />
```

and call:

```typescript
await submitPaymentAttempt(accessToken, registration.id, formData, turnstileToken);
```

If no payment-proof form exists yet, add a test-only assertion to `web/src/lib/api/registrations.test.ts` confirming `submitPaymentAttempt` appends `turnstile_token`, and record in the final handoff that the visible payment-proof insertion waits for the public payment-proof UI.

- [ ] **Step 10: Verify protected public form wiring**

Run:

```powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/api/auth.test.ts src/lib/api/registrations.test.ts
pnpm check
```

Expected: PASS.

- [ ] **Step 11: Commit protected form wiring**

```powershell
git add web/src/routes web/src/lib/states web/src/lib/api web/messages
git commit -m "feat: protect public forms with turnstile"
```

### Task 7: Add Permission Coverage and Deployment Rate-Limit Guidance

**Files:**
- Create: `docs/deployment/security-rate-limits.md`
- Modify: `server/accounts/tests/test_api.py`
- Modify: `server/registrations/tests/test_api.py`
- Modify: `server/tournaments/tests/test_admin.py`
- Modify: `server/tournaments/tests/test_admin_permissions.py`
- Modify: `docs/TODO.md`

**Interfaces:**
- Produces: deployment guidance for Cloudflare WAF and NGINX rate limits.
- Produces: tests confirming participants, staff, and organizer boundaries.

- [ ] **Step 1: Add participant permission regression tests**

In `server/registrations/tests/test_api.py`, add:

```python
def test_participant_cannot_read_another_submitters_registration(self):
    other = create_account(
        email="other@example.com",
        password="strong-password",
        first_name="Other",
        last_name="Player",
    )
    self.client.force_authenticate(user=other)

    response = self.client.get(f"/api/registrations/{self.registration.pk}/")

    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
```

- [ ] **Step 2: Run permission tests and verify behavior**

Run:

```powershell
uv run python manage.py test registrations.tests.test_api tournaments.tests.test_admin tournaments.tests.test_admin_permissions -v 2
```

Expected: PASS. If a participant receives `403` instead of `404`, keep whichever status the current viewset consistently returns and assert that the object data is not exposed.

- [ ] **Step 3: Add deployment guidance doc**

Create `docs/deployment/security-rate-limits.md`:

```markdown
# Security Rate Limits

## Deployment Boundary

Cloudflare WAF and rate limiting protect the backend only when API traffic
passes through a Cloudflare-proxied hostname or Cloudflare Tunnel. If clients
can reach the VPS origin directly, NGINX and Django remain the only backend
protections for those direct requests.

## Sensitive POST Endpoints

- `POST /api/auth/token/`
- `POST /api/auth/register/`
- `POST /api/registrations/submit/`
- `POST /api/registrations/*/payment-attempts/`

## Cloudflare Plan

Create WAF Rate Limiting Rules for the sensitive POST endpoints after final
frontend and API hostnames are selected. Start with conservative thresholds
during beta, monitor false positives, and tighten after real traffic is known.
Use managed WAF rules for generic exploit protection.

## Origin Plan

Configure NGINX `limit_req_zone` and `limit_req` for the same endpoint groups.
Trust `CF-Connecting-IP` only from published Cloudflare source ranges. Return
`429` for rate-limited requests and keep payment-proof upload body limits
explicit.

## Deferred App Limits

Redis-backed Django rate limits are deferred until Redis exists for Channels or
another production runtime need.
```

- [ ] **Step 4: Update TODO only for completed Phase 1 items**

After all tests in Tasks 1-7 pass, mark these TODO items complete:

```markdown
- [x] Finish logout and expose it clearly in the authenticated UI.
- [x] Complete the institution catalogue dropdown in the applicable account
      forms.
- [x] Verify authentication expiry, redirects, error states, and protected
      routes end to end.
- [x] Confirm organizer, staff, and participant permissions without adding
      tournament-specific roles to user accounts.
- [x] Keep entrant and result boundaries capable of supporting solo
      competitors later without implementing the TFT format yet.
- [x] Integrate CloudFlare Turnstile for any user facing area that can be an avenue
      for abuse by bad actors or bots
```

If any item is not fully verified, leave it unchecked and add a short dated note under that checklist item with the remaining condition.

- [ ] **Step 5: Verify docs and permission slice**

Run:

```powershell
uv run python manage.py test accounts.tests.test_api registrations.tests.test_api tournaments.tests.test_admin tournaments.tests.test_admin_permissions -v 2
```

Expected: PASS.

- [ ] **Step 6: Commit permission/docs slice**

```powershell
git add docs/deployment/security-rate-limits.md docs/TODO.md server/accounts/tests/test_api.py server/registrations/tests/test_api.py server/tournaments/tests/test_admin.py server/tournaments/tests/test_admin_permissions.py
git commit -m "docs: record phase one security limits"
```

### Task 8: Final Phase 1 Verification

**Files:**
- Modify only files needed to fix failures found by the commands below.

**Interfaces:**
- Consumes all interfaces from Tasks 1-7.
- Produces a verified Phase 1 foundation suitable for Public UI and Registration phases.

- [ ] **Step 1: Run backend migration and system checks**

```powershell
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run ruff check .
```

Expected:

```text
No changes detected
System check identified no issues (0 silenced).
All checks passed!
```

- [ ] **Step 2: Run focused backend tests**

```powershell
uv run python manage.py test config accounts registrations tournaments -v 2
```

Expected: PASS. If unrelated seed-data tests fail, record the exact failing test names and do not change deferred seed behavior unless it blocks Phase 1.

- [ ] **Step 3: Run focused frontend tests**

```powershell
pnpm exec vitest run src/lib/states/auth-state.test.ts src/lib/components/layout/AppShell.svelte.spec.ts src/lib/components/forms/institution-combobox.svelte.spec.ts src/lib/components/forms/turnstile-widget.svelte.spec.ts src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/api/auth.test.ts src/lib/api/registrations.test.ts
pnpm check
```

Expected: PASS and no Svelte/TypeScript diagnostics.

- [ ] **Step 4: Verify production build key guard**

Run from `web/`:

```powershell
Remove-Item Env:\PUBLIC_TURNSTILE_SITE_KEY -ErrorAction SilentlyContinue; node ./scripts/check-turnstile-env.mjs
```

Expected: exit 1 with:

```text
PUBLIC_TURNSTILE_SITE_KEY is required for production builds.
```

Then run:

```powershell
$env:PUBLIC_TURNSTILE_SITE_KEY='1x00000000000000000000AA'; node ./scripts/check-turnstile-env.mjs
```

Expected: exit 0.

- [ ] **Step 5: Run full frontend unit suite if focused checks are green**

```powershell
pnpm exec vitest run
```

Expected: PASS. Record any unrelated baseline failures separately with file and test names.

- [ ] **Step 6: Inspect final worktree**

```powershell
git status --short --branch
```

Expected: only intentional Phase 1 files are modified or the worktree is clean after commits. Existing unrelated files from before Phase 1 remain untouched unless they were explicitly part of the approved plan.

- [ ] **Step 7: Final Phase 1 commit if verification fixes were needed**

If verification required fixes after Task 7, commit them:

```powershell
git add <only-phase-one-files>
git commit -m "test: verify account security foundation"
```

## Final Handoff Checklist

- [ ] Logout is visible for signed-in users and clears shared auth state.
- [ ] Protected pages redirect consistently on missing or expired sessions.
- [ ] Institution catalogue import, search, custom resolution, and account page integration work.
- [ ] Account APIs do not expose `student_id`, institution review metadata, or account-wide tournament roles.
- [ ] Sign-in, account registration, tournament registration, and payment proof API contracts carry `turnstile_token`.
- [ ] Backend verifies Turnstile before protected mutations outside dev.
- [ ] Missing Turnstile keys bypass only in development and fail outside development.
- [ ] Cloudflare WAF and NGINX rate-limit guidance is documented without claiming the rules are deployed.
- [ ] Phase 1 `docs/TODO.md` items are checked only after passing verification.
