# Secondary Account Navigation Implementation Plan

> **For Codex:** Execute this plan using the subagent-driven-development skill unless the user selects inline execution.

**Goal:** Add a compact secondary navigation bar below the brand header, with public tournament/rules links and locale-aware account controls.

**Architecture:** Keep `AppShell.svelte` as the single navigation owner. Render public controls immediately; on mount, resolve the existing account session and replace the lower-row signed-out controls with localized account controls when a valid user is available. Add a native language `<select>` that preserves the current path while switching locale.

**Tech Stack:** Svelte 5, SvelteKit, TypeScript, Paraglide i18n, Vitest Browser Mode.

**Constraints:** Preserve the existing brand header and routing behavior; do not add a rules route, backend endpoint, cache, or persistence layer. The Rules item is an accessible unavailable stub. Preserve unrelated worktree changes, including `.idea/` and the prior identity-refactor plan.

---

## Task 1: Build and test the public secondary navigation

**Files:**

- Create: `web/src/lib/components/layout/AppShell.svelte.spec.ts`
- Modify: `web/src/lib/components/layout/AppShell.svelte`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`
- Generated: `web/src/lib/i18n/messages.js` (only if `pnpm run paraglide:sync` changes it)

**Step 1: Write the failing public-navigation tests**

Create `AppShell.svelte.spec.ts`. Mock `getAccessToken` to return `null` and `getCurrentUser` so the component cannot make a real request. Render `AppShell` with the raw `children` snippet pattern used by `layout-time-zone.svelte.spec.ts`.

Cover these expectations:

```ts
it('renders a compact public row below the brand header', async () => {
  await renderShell();

  await expect.element(page.getByRole('link', { name: m.nav_tournaments() })).toBeVisible();
  await expect.element(page.getByText(m.nav_rules())).toBeVisible();
  await expect.element(page.getByText(m.nav_rules())).toHaveAttribute('aria-disabled', 'true');
});

it('renders sign-in, register, and the locale selector without a session', async () => {
  await renderShell();

  await expect.element(page.getByRole('link', { name: m.nav_sign_in() })).toBeVisible();
  await expect.element(page.getByRole('link', { name: m.nav_register() })).toBeVisible();
  await expect.element(page.getByRole('combobox', { name: m.locale_switcher_label() })).toBeVisible();
});
```

Run the focused test and confirm it fails because the secondary items and message keys do not yet exist:

```powershell
pnpm exec vitest run --project client src/lib/components/layout/AppShell.svelte.spec.ts
```

**Step 2: Add localization strings**

Add matching keys to both locale files. Use these user-facing strings:

```json
// en.json
"nav_secondary_label": "Secondary navigation",
"nav_rules": "Rules",
"nav_rules_unavailable": "Tournament rules are coming soon.",
"nav_register": "Register",
"nav_welcome": "Welcome, {name}"

// vi.json
"nav_secondary_label": "Điều hướng phụ",
"nav_rules": "Thể lệ",
"nav_rules_unavailable": "Thể lệ chung của giải đấu sắp ra mắt.",
"nav_register": "Đăng ký",
"nav_welcome": "Chào mừng, {name}"
```

Run the configured Paraglide synchronization command from `web/package.json`, inspect the generated diff, and retain generated output only when it changes.

**Step 3: Restructure the navigation and add the locale dropdown**

In `AppShell.svelte`, retain the existing brand link in the original header bar, but remove the account/public links and the EN/VI link group from that bar. Add a visually compact secondary `<nav>` below it with two right-aligned rows:

- Public row: the existing localized Tournaments link and an unavailable Rules `<span>` with `aria-disabled="true"` and its localized `title`.
- Account row: initially signed-out links plus the language dropdown; Task 2 will make the account portion session-aware.

Replace locale anchor links with a labeled native select. Its change handler must preserve the current route and use a full-page locale navigation:

```ts
function changeLocale(event: Event): void {
  const target = event.currentTarget;
  if (!(target instanceof HTMLSelectElement)) return;

  const locale = target.value as Locale;
  if (locale === getLocale()) return;

  window.location.assign(resolve(localizeCurrentHref(page.url, locale)));
}
```

Use a visually-hidden label keyed by `locale_switcher_label`, option labels from `localeName(locale)`, and the current Paraglide locale as the selected value. Keep `data-sveltekit-reload` where an existing locale-switch behavior depends on it; the select itself uses `window.location.assign`.

**Step 4: Run tests and static validation**

```powershell
pnpm run paraglide:sync
pnpm exec vitest run --project client src/lib/components/layout/AppShell.svelte.spec.ts
pnpm check
```

Expected: the focused AppShell test passes. Record any existing unrelated type-check failures without changing unrelated components.

**Step 5: Commit the public navigation change**

```powershell
git add web/src/lib/components/layout/AppShell.svelte web/src/lib/components/layout/AppShell.svelte.spec.ts web/messages/en.json web/messages/vi.json web/src/lib/i18n/messages.js
git commit -m "feat: add secondary public navigation"
```

---

## Task 2: Resolve session state and render locale-aware account controls

**Files:**

- Modify: `web/src/lib/components/layout/AppShell.svelte`
- Modify: `web/src/lib/components/layout/AppShell.svelte.spec.ts`

**Step 1: Write the failing authenticated-state tests**

Extend the AppShell test using mocks for `getAccessToken`, `clearSession`, and `getCurrentUser`. Verify:

- A user with `first_name: 'Thắng'` and `last_name: 'Nguyễn Hữu Quốc'` sees the Profile link named `Welcome, Thắng Nguyễn Hữu Quốc` under the English locale.
- The same user sees `Chào mừng, Nguyễn Hữu Quốc Thắng` under Vietnamese.
- Signed-in users see My registrations beside the welcome/profile link, and not sign-in/register.
- A 401 or 403 from `getCurrentUser` clears the stale session and shows signed-out controls.
- A non-authentication error does not clear the session and does not present signed-out controls as though the user had logged out.

Use a deferred promise or browser assertion that waits for the rendered welcome text so assertions run after `onMount` completes.

Run the focused test and confirm it fails before the state handling is added.

**Step 2: Implement account-navigation state**

Import `onMount`, `getAccessToken`, `clearSession`, `getCurrentUser`, `ApiRequestError`, and `CurrentUser`. Add explicit component state:

```ts
type AccountNavigationState = 'loading' | 'signed-out' | 'signed-in' | 'unavailable';

let accountNavigationState = $state<AccountNavigationState>('loading');
let currentUser = $state<CurrentUser | null>(null);
```

Add a helper that recognizes only `ApiRequestError` statuses 401 and 403. Add a `welcomeName` helper that returns `last_name first_name` when `getLocale() === 'vi'`, otherwise `first_name last_name`.

On mount:

1. Read the existing access token.
2. With no token, set `signed-out` without requesting the API.
3. With a token, call `getCurrentUser`.
4. On success, save the user and set `signed-in`.
5. On 401/403, call `clearSession()` and set `signed-out`.
6. On another failure, set `unavailable`; retain the stored token and show a reserved empty account-control area rather than a misleading signed-out state.

Render the lower account row as:

- `signed-in`: Profile link labeled by `m.nav_welcome({ name: welcomeName(currentUser) })`, then the existing My registrations link.
- `signed-out`: existing Sign in link, then Register link.
- `loading` or `unavailable`: a fixed-height `aria-hidden` placeholder.
- In every state, the locale dropdown remains immediately to the right of the account area.

Use `localizeInternalHref` and `resolve` for Profile, My registrations, Sign in, and Register links. Do not fetch data elsewhere or introduce a global store.

**Step 3: Run the focused suite and project validation**

```powershell
pnpm exec vitest run --project client src/lib/components/layout/AppShell.svelte.spec.ts
pnpm check
```

Expected: all new AppShell scenarios pass; any reported failures must be either fixed in this change or explicitly confirmed baseline failures outside the touched navigation area.

**Step 4: Commit the session-aware navigation**

```powershell
git add web/src/lib/components/layout/AppShell.svelte web/src/lib/components/layout/AppShell.svelte.spec.ts
git commit -m "feat: add account-aware secondary navigation"
```

---

## Task 3: Final verification and handoff

**Files:**

- Inspect only: changed navigation, tests, locale messages, generated Paraglide output

**Step 1: Review the final diff**

Confirm the top navigation remains only the brand header; public controls render in the upper secondary row; all account interactions and the language select render in the lower row; the Rules stub does not navigate to a missing route; and welcome-name ordering is locale-specific.

```powershell
git diff HEAD~2..HEAD -- web/src/lib/components/layout/AppShell.svelte web/src/lib/components/layout/AppShell.svelte.spec.ts web/messages/en.json web/messages/vi.json web/src/lib/i18n/messages.js
git diff --check
git status --short
```

**Step 2: Run proportionate regression checks**

```powershell
pnpm exec vitest run --project client src/lib/components/layout/AppShell.svelte.spec.ts
pnpm exec vitest run --project server
pnpm check
```

Report the focused AppShell result separately. If the known baseline locale-prefix test failures or existing type errors appear again, report them as pre-existing and do not expand scope to repair them. Do not stage or alter `.idea/` or the prior untracked identity-refactor plan.

**Step 3: Handoff**

Summarize the two navigation rows, session fallback behavior, locale name ordering, test evidence, and any pre-existing checks that remain outside this change.
