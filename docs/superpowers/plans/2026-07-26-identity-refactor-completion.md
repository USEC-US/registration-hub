# Identity Refactor Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the account-identity migration by removing stale account-gamer-tag consumers and making all seed data, tests, and registration inputs conform to the current `User` contract.

**Architecture:** Keep the `User` model unchanged: creation requires `email`, `first_name`, and `last_name`, while `school` remains the current account field. Registrations keep gamer tag and school as independent, immutable roster snapshots; the registration page authenticates with an access token but never loads profile values to prefill a roster. A shared test-only account factory makes every backend fixture intentionally valid.

**Tech Stack:** Django 6, Django REST Framework, Python `unittest`, Svelte 5, SvelteKit, TypeScript, Vitest, Playwright browser mode, Paraglide, pnpm, uv

## Global Constraints

- Do not add, restore, or serialize an account-level `gamer_tag` field.
- Keep `User.first_name` and `User.last_name` required by `UserManager.create_user`.
- Keep `school` unchanged; the institution catalogue is outside this plan.
- Do not expose or validate `student_id` beyond existing behavior.
- Do not change RichText/Paraglide typing or redirect-localization behavior.
- Do not modify migrations, registration services, payment workflows, tournament workflows, or Django Admin behavior.

---

## File structure

| Path | Responsibility |
| --- | --- |
| `server/accounts/tests/factories.py` | Test-only helper that creates a valid named user through the real manager. |
| `server/accounts/tests/test_api.py` and `test_models.py` | Account contract tests using names and no account gamer tag. |
| `server/{config,registrations,tournaments}/tests/*.py` | Existing test setup updated to construct valid users. |
| `server/registrations/dev_seed.py` | Deterministic named development accounts without a deleted model field. |
| `server/registrations/tests/test_seed_dev_data_command.py` | Seed assertions aligned with named accounts and no gamer tag. |
| `web/src/lib/components/registrations/RosterEditor.svelte` | Empty roster-snapshot initialization without profile-default props. |
| `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte` | Token-only registration screen; no profile request or stale `CurrentUser` usage. |
| `web/src/routes/*.svelte.spec.ts` and `web/src/lib/components/registrations/registration-flow.svelte.spec.ts` | Updated account fixtures and explicit empty-roster behavior. |
| `web/messages/{en,vi}.json` | Roster gamer-tag label and copy that no longer promises profile prefill. |

### Task 1: Make backend test users conform to the current account contract

**Files:**
- Create: `server/accounts/tests/factories.py`
- Modify: `server/accounts/tests/test_api.py`
- Modify: `server/accounts/tests/test_models.py`
- Modify: `server/config/tests/test_schema_urls.py`
- Modify: `server/registrations/tests/test_admin_actions.py`
- Modify: `server/registrations/tests/test_api.py`
- Modify: `server/registrations/tests/test_models.py`
- Modify: `server/registrations/tests/test_services.py`
- Modify: `server/tournaments/tests/test_admin.py`
- Modify: `server/tournaments/tests/test_admin_permissions.py`
- Modify: `server/tournaments/tests/test_api.py`

**Interfaces:**
- Produces: `create_account(*, email, password, first_name, last_name, **extra_fields) -> User` for tests.
- Preserves: `UserManager.create_user` as the only path that validates required account names.

- [ ] **Step 1: Add an account API regression test for the new payload**

In `server/accounts/tests/test_api.py`, make the registration request send the full current contract and assert the public result contains names but no gamer tag:

```python
response = self.client.post(
    "/api/auth/register/",
    {
        "email": "player@example.com",
        "password": "strong-password-123",
        "first_name": "Minh",
        "last_name": "Nguyen",
        "school": "HCMUS",
    },
    format="json",
)

self.assertEqual(response.status_code, status.HTTP_201_CREATED)
user = get_user_model().objects.get(email="player@example.com")
self.assertEqual(user.first_name, "Minh")
self.assertEqual(user.last_name, "Nguyen")
self.assertEqual(user.school, "HCMUS")
self.assertNotIn("gamer_tag", response.data)
```

Add a 400 assertion for a registration request that omits `first_name` and `last_name`.

- [ ] **Step 2: Run the focused account tests and confirm current stale fixtures fail**

Run: `uv run python manage.py test accounts.tests -v 2`

Expected: FAIL before the fixture changes because direct `create_user` calls omit required names and old gamer-tag assertions reference a deleted field.

- [ ] **Step 3: Add the shared valid-user factory**

Create `server/accounts/tests/factories.py`:

```python
from django.contrib.auth import get_user_model


def create_account(
    *,
    email: str = "player@example.com",
    password: str = "strong-password",
    first_name: str = "Test",
    last_name: str = "User",
    **extra_fields,
):
    return get_user_model().objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        **extra_fields,
    )
```

- [ ] **Step 4: Replace stale test setup with explicit valid users**

Import `create_account` in every listed non-account test module and replace each plain manager call with it. Preserve each test's email, password, staff flags, groups, and object permissions; remove every `gamer_tag=` keyword.

For example, change:

```python
self.owner = get_user_model().objects.create_user(
    email="owner@example.com", password="strong-password"
)
```

to:

```python
self.owner = create_account(
    email="owner@example.com",
    password="strong-password",
    first_name="Owner",
    last_name="Player",
)
```

Use meaningful `first_name` and `last_name` values for staff fixtures as well, e.g. `"Organizer"` / `"Staff"`. Keep direct calls only in `accounts/tests/test_models.py` where a test intentionally verifies that a missing name raises `ValueError`.

Update the current-user PATCH test to patch names and school only:

```python
patch_response = self.client.patch(
    "/api/account/me/",
    {
        "first_name": "New",
        "last_name": "Name",
        "school": "HCMUS",
        "email": "other@example.com",
    },
    format="json",
)
self.assertEqual(user.email, "player@example.com")
self.assertEqual(user.first_name, "New")
self.assertEqual(user.last_name, "Name")
self.assertEqual(user.school, "HCMUS")
```

- [ ] **Step 5: Verify all non-seed backend suites**

Run:

```powershell
uv run python manage.py test accounts config registrations.tests.test_admin_actions registrations.tests.test_api registrations.tests.test_models registrations.tests.test_services tournaments -v 1
```

Expected: PASS. The only deferred backend failures should be seed-command tests, addressed in Task 2.

- [ ] **Step 6: Commit the test-contract repair**

```powershell
git add server/accounts/tests server/config/tests server/registrations/tests server/tournaments/tests
git commit -m "test: align fixtures with account identity"
```

### Task 2: Restore deterministic development seed data

**Files:**
- Modify: `server/registrations/dev_seed.py`
- Modify: `server/registrations/tests/test_seed_dev_data_command.py`

**Interfaces:**
- Consumes: the current user-model fields (`first_name`, `last_name`, `school`, staff flags).
- Produces: the same three deterministic credentialed accounts, with no account-level gamer tag.

- [ ] **Step 1: Add a failing seed assertion for the current identity fields**

In `server/registrations/tests/test_seed_dev_data_command.py`, assert the seeded player has names and no attempted gamer-tag access:

```python
player = get_user_model().objects.get(email=PLAYER_EMAIL)
self.assertEqual(player.first_name, "Development")
self.assertEqual(player.last_name, "Player")
self.assertEqual(player.school, "HCMUS")
self.assertFalse(hasattr(player, "gamer_tag"))
```

Run: `uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2`

Expected: FAIL because `_set_account` passes `gamer_tag` to `update_or_create`.

- [ ] **Step 2: Make `_set_account` persist only real account fields**

Change its signature and persistence fields in `server/registrations/dev_seed.py`:

```python
def _set_account(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    school: str,
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
            "first_name",
            "last_name",
            "school",
            "is_active",
            "is_staff",
            "is_superuser",
        )
    )
    user.groups.set(groups)
    return user
```

Call it with `Development Player`, `Development Organizer`, and `Development Administrator` respectively. Retain `HCMUS` for the player and the current empty `school` values for staff accounts.

- [ ] **Step 3: Verify seed scenarios and the full backend baseline**

Run: `uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2`

Expected: PASS.

Run: `uv run python manage.py test -v 1`

Expected: all 57 backend tests pass.

- [ ] **Step 4: Commit the seed repair**

```powershell
git add server/registrations/dev_seed.py server/registrations/tests/test_seed_dev_data_command.py
git commit -m "fix: update development seed identities"
```

### Task 3: Remove account-profile defaults from registration rosters

**Files:**
- Modify: `web/src/lib/components/registrations/RosterEditor.svelte`
- Modify: `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`
- Modify: `web/src/routes/registration-pages.svelte.spec.ts`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**
- Consumes: `RegistrationMemberInput` snapshot fields and the access token returned by `getAccessToken()`.
- Produces: empty roster snapshot fields, with the first member still captain and ordered first.

- [ ] **Step 1: Rewrite roster-flow tests to assert no account prefill**

Remove `initialGamerTag` and `initialSchool` from component test props. Add an explicit initial-state expectation:

```typescript
expect(members).toEqual([
    {
        gamer_tag_snapshot: '',
        school_snapshot: '',
        is_captain: true,
        display_order: 1
    },
    {
        gamer_tag_snapshot: '',
        school_snapshot: '',
        is_captain: false,
        display_order: 2
    }
]);
```

In `registration-pages.svelte.spec.ts`, remove gamer-tag properties from the mocked `CurrentUser`, assert the profile request is not made, and assert the first roster inputs are empty before the test fills them.

- [ ] **Step 2: Run the focused browser tests and confirm the stale prop/profile assumptions fail**

Run:

```powershell
pnpm exec vitest run --project client src/lib/components/registrations/registration-flow.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts
```

Expected: FAIL before implementation because `RosterEditor` still requires profile-default props and the route still requests `getCurrentUser`.

- [ ] **Step 3: Make roster values registration-owned**

Remove `initialGamerTag` and `initialSchool` from `RosterEditor` props and use empty text when initializing members:

```typescript
interface Props {
    teamSizeMin: number;
    teamSizeMax: number;
    members?: RegistrationMemberInput[];
}

members = Array.from({ length: teamSizeMax }, (_, index) => ({
    gamer_tag_snapshot: '',
    school_snapshot: '',
    is_captain: index === 0,
    display_order: index + 1
}));
```

In the route, remove `getCurrentUser`, `CurrentUser`, `currentUser`, and the profile-loading error path. On mount, set `accessToken = getAccessToken()`, redirect only when it is absent, and otherwise set `loading = false`. Submit when `accessToken` exists and render the form under `{:else if accessToken}`. Pass only team sizes and `bind:members` to `RosterEditor`.

- [ ] **Step 4: Verify focused registration behavior**

Before verification, add the roster-only label to both locale files:

```json
"field_gamer_tag": "Gamer tag"
```

Use `"Tên trong game"` as the Vietnamese value. Delete `registration_loading_profile` and `registration_profile_load_failed` from both files because the registration route no longer loads account-profile defaults.

Then run:

Run:

```powershell
pnpm svelte-kit sync
pnpm exec vitest run --project client src/lib/components/registrations/registration-flow.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the roster-boundary repair**

```powershell
git add web/src/lib/components/registrations/RosterEditor.svelte web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte web/src/lib/components/registrations/registration-flow.svelte.spec.ts web/src/routes/registration-pages.svelte.spec.ts web/messages/en.json web/messages/vi.json
git commit -m "fix: keep roster data out of account profiles"
```

### Task 4: Align account fixtures and translated copy with the completed boundary

**Files:**
- Modify: `web/src/routes/auth-pages.svelte.spec.ts`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**
- Preserves: `CurrentUser = { id, email, first_name, last_name, school }`.
- Produces: translated gamer-tag field labels and account copy that does not promise profile prefill.

- [ ] **Step 1: Update the account-page fixtures before changing messages**

Replace every mocked user such as:

```typescript
const user: CurrentUser = {
    id: 1,
    email: 'player@example.com',
    gamer_tag: 'old-tag',
    school: 'HCMUS'
};
```

with:

```typescript
const user: CurrentUser = {
    id: 1,
    email: 'player@example.com',
    first_name: 'Minh',
    last_name: 'Nguyen',
    school: 'HCMUS'
};
```

Remove gamer-tag inputs and assertions from registration and profile account-page tests. Assert registration and profile requests send `first_name`, `last_name`, and `school` only.

- [ ] **Step 2: Run the account-page tests and confirm the stale fixture failure is resolved**

Run: `pnpm exec vitest run --project client src/routes/auth-pages.svelte.spec.ts`

Expected: PASS.

- [ ] **Step 3: Repair copy that still promises roster prefill**

Update both language files so sign-in, account creation, and profile copy describes account identity and tournament entry without claiming name or school will prefill a roster. For example, replace English profile copy with `"Profile"`, `"Keep your account name and school up to date."`, and `"Submitted roster snapshots remain unchanged."`; provide the equivalent Vietnamese wording. Keep all JSON key sets identical across the two files.

- [ ] **Step 4: Regenerate messages and verify the identity frontend surface**

Run:

```powershell
pnpm svelte-kit sync
pnpm exec vitest run --project client src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts
```

Expected: PASS.

Run: `pnpm check`

Expected: no errors involving `CurrentUser.gamer_tag`, `field_gamer_tag`, `RosterEditor` props, or the registration route. RichText/Paraglide errors may remain and must be recorded rather than changed.

- [ ] **Step 5: Commit the frontend contract and copy repair**

```powershell
git add web/src/routes/auth-pages.svelte.spec.ts web/messages/en.json web/messages/vi.json web/src/lib/paraglide
git commit -m "fix: align account UI with identity contract"
```

### Task 5: Perform scoped verification and document remaining baseline failures

**Files:**
- Modify only if generated by the approved Paraglide sync: `web/src/lib/paraglide/**`

**Interfaces:**
- Verifies: completed account identity and roster boundaries.
- Does not alter: RichText typing or navigation-localization behavior.

- [ ] **Step 1: Run backend schema, lint, and test verification**

```powershell
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run ruff check .
uv run python manage.py test -v 1
```

Expected: `No changes detected`, `System check identified no issues`, `All checks passed!`, and all backend tests pass.

- [ ] **Step 2: Run deterministic frontend checks**

```powershell
pnpm exec vitest run --project server
pnpm check
```

Expected: the identity-specific type errors are absent. Record the known RichText/Paraglide diagnostics and navigation-localization expectation failures separately; do not modify those systems in this plan.

- [ ] **Step 3: Inspect the final worktree**

```powershell
git status --short --branch
git diff --check
```

Expected: no unintended changes. Preserve the user-owned untracked `.idea/` directory.

- [ ] **Step 4: Commit any approved generated Paraglide output**

```powershell
git add web/src/lib/paraglide
git commit -m "chore: regenerate message bindings"
```

Only run this commit if `pnpm svelte-kit sync` changed generated Paraglide files.
