# Test Health Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every declared frontend and backend quality gate reliable while preserving Vietnamese as the unprefixed default locale.

**Architecture:** Tests will state the existing Paraglide routing contract explicitly: Vietnamese pages use bare paths and English pages use `/en/`. A browser-only Vitest setup supplies the dynamic public API environment. No production route or API contract is added; E2E tests use the existing sign-in route, roster edits use immutable bound-array replacements, and schema metadata makes OpenAPI generation deterministic.

**Tech Stack:** Svelte 5, SvelteKit, Vitest Browser Mode, Playwright, Paraglide, Django 6, Django REST Framework, drf-spectacular, Ruff, Prettier.

## Global Constraints

- Keep `project.inlang/settings.json` unchanged: `baseLocale` is `vi`.
- Vietnamese paths are bare; English paths begin with `/en/`.
- Do not add a production-only test route or make E2E calls to a live Django API.
- Do not change registration authorization, API response fields, migrations, or models.
- Stage and commit only task files; never stage `.superpowers/sdd/progress.md`.

---

### Task 1: Make locale and browser-environment tests deterministic

**Files:**
- Create: `web/src/test/browser.setup.ts`
- Modify: `web/vite.config.ts`
- Modify: `web/src/lib/navigation.test.ts`
- Modify: `web/src/routes/public-pages.svelte.spec.ts`
- Modify: `web/src/routes/auth-pages.svelte.spec.ts`
- Modify: `web/src/routes/registration-pages.svelte.spec.ts`
- Test: the modified Vitest files plus `design-system.svelte.spec.ts` and `layout-time-zone.svelte.spec.ts`

**Interfaces:**
- Consumes: Paraglide `overwriteGetLocale`, `localizeHref`, and the virtual `$env/dynamic/public` module.
- Produces: deterministic browser imports and assertions that distinguish bare Vietnamese from `/en/` English routes.

- [ ] **Step 1: Preserve the existing red state**

~~~
pnpm exec vitest run src/lib/navigation.test.ts src/routes/public-pages.svelte.spec.ts src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/design-system.svelte.spec.ts src/routes/layout-time-zone.svelte.spec.ts
~~~

Expected: locale-path assertions fail and the design-system/time-zone suites fail while importing `$env/dynamic/public`.

- [ ] **Step 2: Make locale selection explicit in the tests**

In `navigation.test.ts`, set `vi` in both `beforeEach` and `afterEach`. Unsafe input fallbacks must assert `/account/registrations`; add an English assertion:

~~~ts
it('prefixes the fallback when English is selected', () => {
  overwriteGetLocale(() => 'en');
  expect(sanitizeInternalRedirect(null)).toBe('/en/account/registrations');
});
~~~

In the route specs, keep English fixtures explicit and update their generated links and redirects to `/en/...`. Keep Vietnamese fixtures explicit and update their links and redirects to bare paths. Add a `beforeEach(() => overwriteGetLocale(() => 'en'))` to the public-pages spec so its English-copy tests never rely on generated-runtime state.

- [ ] **Step 3: Add the shared browser environment fixture**

Create `web/src/test/browser.setup.ts`:

~~~ts
import { vi } from 'vitest';

vi.mock('$env/dynamic/public', () => ({
  env: { PUBLIC_API_BASE_URL: '/api' }
}));
~~~

Add this only to the client project in `web/vite.config.ts`:

~~~ts
setupFiles: ['./src/test/browser.setup.ts']
~~~

- [ ] **Step 4: Verify the repaired browser tests**

~~~
pnpm exec vitest run src/lib/navigation.test.ts src/routes/public-pages.svelte.spec.ts src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/design-system.svelte.spec.ts src/routes/layout-time-zone.svelte.spec.ts
~~~

Expected: all selected files pass; no suite throws `Cannot read properties of undefined (reading 'env')`.

- [ ] **Step 5: Commit**

~~~
git add web/src/test/browser.setup.ts web/vite.config.ts web/src/lib/navigation.test.ts web/src/routes/public-pages.svelte.spec.ts web/src/routes/auth-pages.svelte.spec.ts web/src/routes/registration-pages.svelte.spec.ts
git commit -m "test: align frontend locale contract"
~~~

### Task 2: Restore production-preview E2E coverage

**Files:**
- Modify: `web/src/routes/public-registration.e2e.ts`
- Modify: `web/package.json`
- Test: `web/src/routes/public-registration.e2e.ts`

**Interfaces:**
- Consumes: existing sign-in, home, tournament-detail, and registration routes plus intercepted `/api/tournaments/` requests.
- Produces: three browser tests that work against a production preview without a synthetic route or browser download.

- [ ] **Step 1: Preserve the missing-fixture failure**

~~~
pnpm exec playwright test --grep "browser navigation runs public"
~~~

Expected: the smoke test fails because `/demo/playwright` returns 404.

- [ ] **Step 2: Start browser flows from the existing sign-in route**

In each E2E test that starts at `/demo/playwright`, replace the entry with:

~~~ts
await page.goto('/auth/sign-in');
await page.locator('a[href="/"]').first().click();
~~~

Assert the real Vietnamese default page and deterministic URLs:

~~~ts
await expect(page).toHaveURL('/');
await expect(page.getByRole('heading', {
  level: 1,
  name: 'Cổng Đăng ký Giải đấu'
})).toBeVisible();
await page.getByRole('link', { name: tournament.name }).first().click();
await expect(page.locator(
  'a[href="/tournaments/usec-summer-2026/games/9/register"]'
)).toBeVisible();
~~~

For the profile redirect, retain the bare redirect URL and assert `Đăng nhập tài khoản`. For the registration redirect, assert document paths `['/auth/sign-in', '/auth/sign-in']` and retain the assertion that no document request ends in `/register`.

- [ ] **Step 3: Separate browser setup from test execution**

Replace the scripts in `web/package.json` with:

~~~json
"test:e2e": "playwright test",
"test:e2e:install": "playwright install"
~~~

- [ ] **Step 4: Verify and commit**

~~~
pnpm run test:e2e
git add web/src/routes/public-registration.e2e.ts web/package.json
git commit -m "test: restore frontend e2e coverage"
~~~

Expected: all three scenarios pass without requesting `/demo/playwright`.

### Task 3: Make roster text edits reactive

**Files:**
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`
- Modify: `web/src/lib/components/registrations/RosterEditor.svelte`
- Test: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`

**Interfaces:**
- Consumes: the `$bindable` `members: RegistrationMemberInput[]` prop.
- Produces: a new `RegistrationMemberInput[]` assignment for each gamer-tag or school edit.

- [ ] **Step 1: Write the failing propagation test**

Add a two-member render with a setter counter. Reset the counter after initial member creation, fill both first-member fields, and assert that the parent setter receives two updates:

~~~ts
let members: RegistrationMemberInput[] = [];
let memberUpdates = 0;
render(RosterEditor, {
  teamSizeMin: 2,
  teamSizeMax: 2,
  get members() { return members; },
  set members(value) { members = value; memberUpdates += 1; }
});
memberUpdates = 0;

await page.getByLabelText('Gamer tag').fill('captain');
await page.getByLabelText('School').fill('HCMUS');

expect(members[0]).toMatchObject({
  gamer_tag_snapshot: 'captain',
  school_snapshot: 'HCMUS'
});
expect(memberUpdates).toBe(2);
~~~

- [ ] **Step 2: Verify red**

~~~
pnpm exec vitest run src/lib/components/registrations/registration-flow.svelte.spec.ts
~~~

Expected: the new assertion reports no setter calls after nested bindings change text.

- [ ] **Step 3: Implement immutable member updates**

Add this helper in `RosterEditor.svelte`:

~~~ts
function updateMember(
  index: number,
  field: 'gamer_tag_snapshot' | 'school_snapshot',
  event: Event
): void {
  const value = (event.currentTarget as HTMLInputElement).value;
  members = members.map((member, memberIndex) =>
    memberIndex === index ? { ...member, [field]: value } : member
  );
}
~~~

Replace each nested binding with:

~~~svelte
value={member.gamer_tag_snapshot}
oninput={(event) => updateMember(index, 'gamer_tag_snapshot', event)}
~~~

and:

~~~svelte
value={member.school_snapshot}
oninput={(event) => updateMember(index, 'school_snapshot', event)}
~~~

- [ ] **Step 4: Verify and commit**

~~~
pnpm exec vitest run src/lib/components/registrations/registration-flow.svelte.spec.ts
git add web/src/lib/components/registrations/RosterEditor.svelte web/src/lib/components/registrations/registration-flow.svelte.spec.ts
git commit -m "fix: propagate reactive roster member edits"
~~~

Expected: propagation and captain tests pass with no `binding_property_non_reactive` warning.

### Task 4: Make OpenAPI generation warning-free

**Files:**
- Modify: `server/config/tests/test_schema_urls.py`
- Modify: `server/registrations/views.py`
- Modify: `server/config/settings.py`
- Test: `server/config/tests/test_schema_urls.py`

**Interfaces:**
- Consumes: `RegistrationViewSet.get_queryset`, registration/payment status `TextChoices`, and the schema endpoint.
- Produces: integer registration path parameters plus stable `RegistrationStatus` and `PaymentAttemptStatus` components.

- [ ] **Step 1: Add failing schema contract assertions**

Request JSON schema in the debug schema test and assert:

~~~py
schema_response = self.client.get(
  '/api/schema/', HTTP_ACCEPT='application/vnd.oai.openapi+json'
)
schema = schema_response.json()

self.assertEqual(
  schema['paths']['/api/registrations/{id}/']['get']['parameters'][0]['schema']['type'],
  'integer',
)
self.assertIn('RegistrationStatus', schema['components']['schemas'])
self.assertIn('PaymentAttemptStatus', schema['components']['schemas'])
~~~

- [ ] **Step 2: Verify red**

~~~
& .\.venv\Scripts\python.exe manage.py test config.tests.test_schema_urls -v 2 --keepdb --noinput
~~~

Expected: the parameter is inferred as `string` and the requested enum components are absent.

- [ ] **Step 3: Add schema-only metadata**

In `RegistrationViewSet`, keep the request-user-filtered `get_queryset` and add:

~~~py
queryset = Registration.objects.none()
~~~

In `server/config/settings.py`, add:

~~~py
SPECTACULAR_SETTINGS = {
  'ENUM_NAME_OVERRIDES': {
    'RegistrationStatus': 'registrations.models.Registration.Status',
    'PaymentAttemptStatus': 'registrations.models.PaymentAttempt.Status',
  }
}
~~~

`RegistrationStatusEvent.to_status` uses `Registration.Status`, so it resolves to the same registration enum instead of creating another `ToStatusEnum`.

- [ ] **Step 4: Verify and commit**

~~~
& .\.venv\Scripts\python.exe manage.py test config.tests.test_schema_urls -v 2 --keepdb --noinput
& .\.venv\Scripts\python.exe manage.py test -v 2 --keepdb --noinput
git add server/config/tests/test_schema_urls.py server/registrations/views.py server/config/settings.py
git commit -m "fix: stabilize OpenAPI registration schema"
~~~

Expected: backend tests pass with no queryset, untyped-path, or enum-collision schema warnings.

### Task 5: Format and run final gates

**Files:**
- Modify: only source files rewritten by the repository's Prettier configuration.
- Test: all declared frontend and backend quality commands.

**Interfaces:**
- Consumes: the existing Prettier, ESLint, Vitest, Playwright, Django, and Ruff commands.
- Produces: a clean style gate and final regression evidence.

- [ ] **Step 1: Apply formatting**

~~~
pnpm run format
~~~

Expected: Prettier rewrites the 85 reported frontend files without behavioral changes.

- [ ] **Step 2: Verify frontend gates**

~~~
pnpm run check
pnpm run lint
pnpm run test:unit -- --run
pnpm run test:e2e
~~~

Expected: type/i18n checks, Prettier, ESLint, all Vitest projects, and all Playwright scenarios pass.

- [ ] **Step 3: Verify backend gates**

~~~
& .\.venv\Scripts\ruff.exe check .
& .\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
& .\.venv\Scripts\python.exe manage.py test -v 2 --keepdb --noinput
~~~

Expected: Ruff is clean, Django reports no model changes, and the full suite passes without schema warnings.

- [ ] **Step 4: Review and commit formatting**

~~~
git diff --check
git status --short
git add web
git commit -m "style: format frontend source"
~~~

Before committing, unstage `.superpowers/sdd/progress.md` if it appears staged. The final diff must contain no generated test artifacts.

