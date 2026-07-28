# AuthState Consumer Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Migrate AppShell, the profile page, and the sign-in page to the existing shared authState without changing other authentication consumers.

**Architecture:** Each migrated component uses the singleton from web/src/lib/states/auth-state.svelte.ts. authState owns session/current-user changes and redirects; components retain their own form fields, pending states, validation messages, and navigation UI.

**Tech Stack:** Svelte 5, SvelteKit 2, TypeScript, Vitest 4 browser tests, existing authState unit tests.

## Global Constraints

- Modify only AppShell, profile, sign-in, and their existing tests.
- Do not modify the AuthState public API, registration page, registration/payment pages, sign-out behavior, or server API.
- The empty, untracked sign-out route has been deleted with user authorization; do not add or modify any sign-out behavior or existing shell link.
- Use authState for session/current-user work; keep profile updateCurrentUser as a raw profile API request.
- AppShell initialization must not redirect public pages.
- Sign-in navigates only after authState.signIn() returns a CurrentUser; null stays on the form with the generic sign-in error.

---

## File structure

| File | Responsibility |
| --- | --- |
| web/src/lib/components/layout/AppShell.svelte | Initialize and render shared auth state in account navigation. |
| web/src/lib/components/layout/AppShell.svelte.spec.ts | Assert shared-state shell navigation without direct API/session mocks. |
| web/src/routes/account/profile/+page.svelte | Guard, hydrate, save, and display profile using shared auth state. |
| web/src/routes/auth/sign-in/+page.svelte | Delegate sign-in/session setup to authState. |
| web/src/routes/auth-pages.svelte.spec.ts | Verify profile and sign-in delegation while retaining registration coverage. |

## Task 1: Migrate AppShell to authState

**Files:**

- Modify: web/src/lib/components/layout/AppShell.svelte
- Modify: web/src/lib/components/layout/AppShell.svelte.spec.ts

**Interfaces:**

- Consumes: authState.initialize(): Promise<CurrentUser | null>, authState.status, authState.currentUser.
- Produces: Account navigation that reacts to shared signed-in and signed-out state.
- Does not consume getCurrentUser, getAccessToken, clearSession, or ApiRequestError.

- [ ] **Step 1: Rewrite shell tests to use a shared-state boundary mock**

In AppShell.svelte.spec.ts, replace the direct API/session imports and mocks with this hoisted singleton mock:

~~~ts
const authStateMock = vi.hoisted(() => ({
	status: 'idle',
	currentUser: null as CurrentUser | null,
	initialize: vi.fn()
}));

vi.mock('$lib/states/auth-state.svelte', () => ({ authState: authStateMock }));
~~~

Reset it in beforeEach:

~~~ts
authStateMock.status = 'idle';
authStateMock.currentUser = null;
authStateMock.initialize.mockReset().mockResolvedValue(null);
~~~

Update the signed-in tests so they set the state before render and assert initialization:

~~~ts
authStateMock.status = 'signed-in';
authStateMock.currentUser = user;
authStateMock.initialize.mockResolvedValue(user);

renderShell();

await expect(
	page.getByRole('link', { name: m.nav_welcome({ name: 'Thắng Nguyễn Hữu Quốc' }) })
).toBeVisible();
expect(authStateMock.initialize).toHaveBeenCalledOnce();
~~~

Replace stale-session and unavailable tests with direct rendering state assertions. The AuthState unit suite already owns the HTTP status behavior:

~~~ts
it('renders public account controls from shared signed-out state', async () => {
	authStateMock.status = 'signed-out';
	renderShell();

	await expect.element(page.getByRole('link', { name: m.nav_sign_in() })).toBeVisible();
	await expect.element(page.getByRole('link', { name: m.nav_register() })).toBeVisible();
});

it('keeps account controls unavailable from shared unavailable state', () => {
	authStateMock.status = 'unavailable';
	const { container } = renderShell();

	expect(container.querySelector('a[href="/auth/sign-in"]')).toBeNull();
	expect(container.querySelector('a[href="/auth/register"]')).toBeNull();
});
~~~

- [ ] **Step 2: Run the shell spec and verify it fails**

Run from web/:

~~~powershell
pnpm exec vitest run src/lib/components/layout/AppShell.svelte.spec.ts
~~~

Expected: tests fail because AppShell still imports and renders its local auth state.

- [ ] **Step 3: Replace local shell auth state with the singleton**

In AppShell.svelte:

1. Remove imports for getCurrentUser, ApiRequestError, getAccessToken, and clearSession.
2. Add this import while retaining CurrentUser as a type import for welcomeName:

~~~ts
import { authState } from '$lib/states/auth-state.svelte';
~~~

3. Remove AccountNavigationState, accountNavigationState, currentUser, and isAuthenticationError.
4. Replace the onMount block with:

~~~ts
onMount(() => {
	void authState.initialize();
});
~~~

5. Change the signed-in branch to use the shared reactive values:

~~~svelte
{#if authState.status === 'signed-in' && authState.currentUser}
	<a
		class="flex items-center border-(--line) px-4 py-2 text-sm font-medium"
		href={resolve(localizeInternalHref('/account/profile'))}
	>
		{m.nav_welcome({ name: welcomeName(authState.currentUser) })}
	</a>
~~~

6. Change the signed-out branch condition to authState.status === 'signed-out'. Leave every other markup line, including any existing sign-out link, unchanged.

- [ ] **Step 4: Run the shell spec and verify it passes**

Run from web/:

~~~powershell
pnpm exec vitest run src/lib/components/layout/AppShell.svelte.spec.ts
~~~

Expected: all AppShell tests pass, including locale-specific name order and signed-out navigation.

- [ ] **Step 5: Commit the shell migration**

~~~powershell
git add web/src/lib/components/layout/AppShell.svelte web/src/lib/components/layout/AppShell.svelte.spec.ts
git commit -m "refactor: migrate shell to auth state"
~~~

## Task 2: Migrate profile hydration and cache updates

**Files:**

- Modify: web/src/routes/account/profile/+page.svelte
- Modify: web/src/routes/auth-pages.svelte.spec.ts

**Interfaces:**

- Consumes: authState.requireAccessToken(): string | null, authState.initialize(): Promise<CurrentUser | null>, authState.status, authState.handleAuthenticationError(cause): boolean, and authState.updateCurrentUser(user): void.
- Consumes: updateCurrentUser(accessToken, payload) from $lib/api/auth.
- Produces: profile UI with no direct token lookup, current-user request, session clearing, or local currentUser state.

- [ ] **Step 1: Extend auth-page tests with an authState mock and failing profile assertions**

Add a shared-state mock to auth-pages.svelte.spec.ts, preserving the existing raw signIn import because the registration page continues to use it:

~~~ts
const authStateMock = vi.hoisted(() => ({
	status: 'idle',
	currentUser: null as CurrentUser | null,
	initialize: vi.fn(),
	requireAccessToken: vi.fn(),
	handleAuthenticationError: vi.fn(),
	updateCurrentUser: vi.fn(),
	signIn: vi.fn()
}));

vi.mock('$lib/states/auth-state.svelte', () => ({ authState: authStateMock }));
~~~

Add this existing message import because the new null-hydration test asserts the localized generic error:

~~~ts
import * as m from '$lib/paraglide/messages';
~~~

Reset it in beforeEach:

~~~ts
authStateMock.status = 'idle';
authStateMock.currentUser = null;
authStateMock.initialize.mockReset();
authStateMock.requireAccessToken.mockReset();
authStateMock.handleAuthenticationError.mockReset().mockReturnValue(false);
authStateMock.updateCurrentUser.mockReset();
authStateMock.signIn.mockReset();
~~~

Change the successful profile-save test setup and assertions to this contract:

~~~ts
authStateMock.requireAccessToken.mockReturnValue(tokens.access);
authStateMock.initialize.mockResolvedValue(user);
authStateMock.currentUser = user;
authStateMock.updateCurrentUser.mockClear();

await vi.waitFor(() => expect(authStateMock.initialize).toHaveBeenCalledOnce());
await page.getByRole('button', { name: 'Save profile' }).click();

await vi.waitFor(() =>
	expect(authStateMock.updateCurrentUser).toHaveBeenCalledWith({
		...user,
		school: 'HCMUS - VNU'
	})
);
~~~

Replace the missing-token test with an assertion that the page delegates to the guard and renders its redirecting UI:

~~~ts
authStateMock.requireAccessToken.mockReturnValue(null);
render(ProfilePage);

await vi.waitFor(() => expect(authStateMock.requireAccessToken).toHaveBeenCalledOnce());
await expect.element(page.getByText(m.auth_redirecting_to_sign_in())).toBeVisible();
~~~

Add a null-user test for the approved non-auth behavior:

~~~ts
authStateMock.requireAccessToken.mockReturnValue(tokens.access);
authStateMock.initialize.mockResolvedValue(null);
authStateMock.status = 'unavailable';
render(ProfilePage);

await expect.element(page.getByText(m.profile_load_failed())).toBeVisible();
expect(authStateMock.handleAuthenticationError).not.toHaveBeenCalled();
~~~

- [ ] **Step 2: Run the profile tests and verify they fail**

Run from web/:

~~~powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts
~~~

Expected: profile tests fail because the page still reads session helpers and calls getCurrentUser directly.

- [ ] **Step 3: Replace profile session and current-user logic**

In profile/+page.svelte:

1. Remove imports for resolve, page, ApiRequestError, getCurrentUser, CurrentUser, replaceInternalLocation, clearSession, getAccessToken, and localizeInternalHref.
2. Keep updateCurrentUser and add:

~~~ts
import { authState } from '$lib/states/auth-state.svelte';
~~~

3. Remove accessToken, currentUser, signInHref, redirectToSignIn, and isAuthenticationError. Keep form-field and presentation state.
4. Replace onMount with this flow:

~~~ts
onMount(async () => {
	const accessToken = authState.requireAccessToken();
	if (!accessToken) {
		redirecting = true;
		loading = false;
		return;
	}

	const user = await authState.initialize();
	if (!user) {
		if (authState.status === 'signed-out') {
			redirecting = true;
			authState.requireAccessToken();
		} else {
			formErrors = [m.profile_load_failed()];
		}
		loading = false;
		return;
	}

	firstName = user.first_name;
	lastName = user.last_name;
	school = user.school;
	loading = false;
});
~~~

5. In handleSubmit, obtain the token at the beginning:

~~~ts
const accessToken = authState.requireAccessToken();
if (saving || !accessToken) {
	if (!accessToken) redirecting = true;
	return;
}
~~~

6. Replace the successful local assignment with:

~~~ts
const user = await updateCurrentUser(accessToken, {
	first_name: firstName,
	last_name: lastName,
	school
});
authState.updateCurrentUser(user);
firstName = user.first_name;
lastName = user.last_name;
school = user.school;
saved = true;
~~~

7. Replace the authentication-error branch with:

~~~ts
if (authState.handleAuthenticationError(cause)) {
	redirecting = true;
	return;
}
~~~

8. Render the email and profile card only when authState.currentUser is present:

~~~svelte
{:else if authState.currentUser}
	<!-- retain the existing card markup -->
	<dd class="font-mono-data mt-2 break-all text-sm">{authState.currentUser.email}</dd>
~~~

- [ ] **Step 4: Run the profile tests and verify they pass**

Run from web/:

~~~powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts
~~~

Expected: the profile section passes while existing registration-page tests retain their current behavior.

- [ ] **Step 5: Commit the profile migration**

~~~powershell
git add web/src/routes/account/profile/+page.svelte web/src/routes/auth-pages.svelte.spec.ts
git commit -m "refactor: migrate profile to auth state"
~~~

## Task 3: Delegate sign-in to authState

**Files:**

- Modify: web/src/routes/auth/sign-in/+page.svelte
- Modify: web/src/routes/auth-pages.svelte.spec.ts

**Interfaces:**

- Consumes: authState.signIn(email, password): Promise<CurrentUser | null>.
- Consumes: sanitizeInternalRedirect and goto for successful navigation.
- Produces: sign-in that keeps form-specific API errors and does not navigate after a null hydration result.

- [ ] **Step 1: Replace sign-in test expectations with the shared-state contract**

In the sign-in test section, set:

~~~ts
authStateMock.signIn.mockResolvedValue(user);
~~~

Then assert delegated sign-in and navigation without direct token storage:

~~~ts
await page.getByRole('button', { name: 'Sign in' }).click();

await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/account/registrations'));
expect(authStateMock.signIn).toHaveBeenCalledWith('player@example.com', 'strong-password');
expect(saveSession).not.toHaveBeenCalled();
~~~

Add this test for the approved hydration-failure UX:

~~~ts
it('stays on the form when sign-in cannot hydrate the current user', async () => {
	authStateMock.signIn.mockResolvedValue(null);
	render(SignInPage);

	await page.getByLabelText('Email').fill('player@example.com');
	await page.getByLabelText('Password').fill('strong-password');
	await page.getByRole('button', { name: 'Sign in' }).click();

	await expect.element(page.getByText(m.auth_sign_in_failed())).toBeVisible();
	expect(goto).not.toHaveBeenCalled();
});
~~~

- [ ] **Step 2: Run the sign-in tests and verify they fail**

Run from web/:

~~~powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts
~~~

Expected: sign-in assertions fail because the page still calls the raw signIn API and saveSession.

- [ ] **Step 3: Delegate the sign-in page to authState**

In auth/sign-in/+page.svelte:

1. Remove the raw signIn and saveSession imports.
2. Add:

~~~ts
import { authState } from '$lib/states/auth-state.svelte';
~~~

3. Replace the successful authentication branch in handleSubmit with:

~~~ts
const user = await authState.signIn(email, password);
if (!user) {
	formErrors = [m.auth_sign_in_failed()];
	return;
}

await goto(resolve(sanitizeInternalRedirect(page.url.searchParams.get('redirectTo'))));
~~~

Leave the catch block and all existing form/error markup unchanged.

- [ ] **Step 4: Run the sign-in tests and verify they pass**

Run from web/:

~~~powershell
pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts
~~~

Expected: sign-in delegates to authState, preserves credential error rendering, and remains on the form after a null hydration result.

- [ ] **Step 5: Run full frontend verification**

Run from web/:

~~~powershell
pnpm exec vitest run
pnpm check
pnpm lint
~~~

Expected: each command exits with code 0 and no test, type, formatting, or lint failures.

- [ ] **Step 6: Commit the sign-in migration**

~~~powershell
git add web/src/routes/auth/sign-in/+page.svelte web/src/routes/auth-pages.svelte.spec.ts
git commit -m "refactor: migrate sign-in to auth state"
~~~

## Final review checklist

- [ ] AppShell, profile, and sign-in are the only migrated consumers.
- [ ] AppShell and public pages do not redirect during shared-state initialization.
- [ ] Profile updates replace the shared current-user cache.
- [ ] Sign-in does not navigate after a null user hydration result.
- [ ] Registration and all remaining sign-out behavior are unchanged.
- [ ] Focused specs, complete unit suite, pnpm check, and pnpm lint have fresh passing output.
