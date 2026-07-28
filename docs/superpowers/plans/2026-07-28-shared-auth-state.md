# Shared AuthState Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add a tested, client-only Svelte 5 AuthState singleton that owns session restoration, the current-user cache, sign-in/out, access-token refresh, and redirecting authentication guards.

**Architecture:** AuthState is a rune-backed singleton in web/src/lib/auth/auth-state.svelte.ts. It coordinates existing raw HTTP, localStorage, and replace-navigation modules. Registration remains a raw API action and existing consumers are not migrated in this increment.

**Tech Stack:** Svelte 5 runes, SvelteKit 2, TypeScript, Vitest 4.

## Global Constraints

- Keep registration in web/src/lib/api/auth.ts; do not add a registration method to AuthState.
- Do not modify AppShell, profile, protected registration pages, payment callbacks, or sign-out route.
- Preserve every pre-existing uncommitted change.
- All localStorage, network, and navigation work is browser-only; server-side state is inert.
- Only HTTP 401 and 403 clear a session and redirect. Other failures remain non-auth failures.

---

## File structure

| File | Responsibility |
| --- | --- |
| web/src/lib/auth/auth-state.svelte.ts | Reactive AuthState class and application singleton. |
| web/src/lib/auth/auth-state.test.ts | Node Vitest contract tests for state transitions and redirects. |

## Task 1: Implement reactive session and current-user lifecycle

**Files:**

- Create: web/src/lib/auth/auth-state.svelte.ts
- Create: web/src/lib/auth/auth-state.test.ts

**Interfaces:**

- Consumes: getCurrentUser, signIn, and refreshAccessToken from $lib/api/auth; session helpers from $lib/auth/session; ApiRequestError.
- Produces: AuthStatus, AuthState, and auth.
- Signatures: initialize(): Promise<CurrentUser | null>; signIn(email, password): Promise<CurrentUser | null>; signOut(): void; refreshSession(): Promise<string | null>; updateCurrentUser(user): void.

- [ ] **Step 1: Write the failing lifecycle tests**

Create web/src/lib/auth/auth-state.test.ts. Mock only the HTTP and storage boundaries, construct a new AuthState per test, and use this complete test contract:

~~~ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '$lib/api/client';
import type { CurrentUser, TokenPair } from '$lib/api/types';

const testState = vi.hoisted(() => ({
	access: null as string | null,
	refresh: null as string | null,
	getCurrentUser: vi.fn(),
	requestSignIn: vi.fn(),
	refreshAccessToken: vi.fn(),
	saveSession: vi.fn(),
	clearSession: vi.fn()
}));

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/api/auth', () => ({
	getCurrentUser: testState.getCurrentUser,
	signIn: testState.requestSignIn,
	refreshAccessToken: testState.refreshAccessToken
}));
vi.mock('$lib/auth/session', () => ({
	getAccessToken: () => testState.access,
	getRefreshToken: () => testState.refresh,
	saveSession: (tokens: TokenPair) => {
		testState.saveSession(tokens);
		testState.access = tokens.access;
		testState.refresh = tokens.refresh;
	},
	clearSession: () => {
		testState.clearSession();
		testState.access = null;
		testState.refresh = null;
	}
}));

const { AuthState } = await import('./auth-state.svelte');

const currentUser: CurrentUser = {
	id: 7,
	email: 'player@example.com',
	first_name: 'Minh',
	last_name: 'Nguyen',
	school: 'HCMUS'
};

beforeEach(() => {
	testState.access = null;
	testState.refresh = null;
	testState.getCurrentUser.mockReset();
	testState.requestSignIn.mockReset();
	testState.refreshAccessToken.mockReset();
	testState.saveSession.mockClear();
	testState.clearSession.mockClear();
});

describe('AuthState lifecycle', () => {
	it('sets signed-out without requesting a user when storage has no token', async () => {
		const auth = new AuthState();
		await expect(auth.initialize()).resolves.toBeNull();
		expect(auth.status).toBe('signed-out');
		expect(auth.currentUser).toBeNull();
		expect(testState.getCurrentUser).not.toHaveBeenCalled();
	});

	it('hydrates the current user from a stored token', async () => {
		testState.access = 'access-token';
		testState.getCurrentUser.mockResolvedValue(currentUser);
		const auth = new AuthState();
		await expect(auth.initialize()).resolves.toEqual(currentUser);
		expect(auth.status).toBe('signed-in');
		expect(auth.currentUser).toEqual(currentUser);
		expect(testState.getCurrentUser).toHaveBeenCalledWith('access-token');
	});

	it('shares one in-flight user request', async () => {
		testState.access = 'access-token';
		let resolveUser!: (user: CurrentUser) => void;
		testState.getCurrentUser.mockReturnValue(
			new Promise<CurrentUser>((resolve) => {
				resolveUser = resolve;
			})
		);
		const auth = new AuthState();
		const first = auth.initialize();
		const second = auth.initialize();
		resolveUser(currentUser);
		await expect(Promise.all([first, second])).resolves.toEqual([currentUser, currentUser]);
		expect(testState.getCurrentUser).toHaveBeenCalledTimes(1);
	});

	it('persists credentials and hydrates the user on sign-in', async () => {
		testState.requestSignIn.mockResolvedValue({ access: 'new-access', refresh: 'new-refresh' });
		testState.getCurrentUser.mockResolvedValue(currentUser);
		const auth = new AuthState();
		await expect(auth.signIn('player@example.com', 'password')).resolves.toEqual(currentUser);
		expect(testState.saveSession).toHaveBeenCalledWith({
			access: 'new-access',
			refresh: 'new-refresh'
		});
		expect(auth.currentUser).toEqual(currentUser);
	});

	it('preserves the refresh token while refreshing the access token', async () => {
		testState.refresh = 'refresh-token';
		testState.refreshAccessToken.mockResolvedValue({ access: 'fresh-access' });
		const auth = new AuthState();
		await expect(auth.refreshSession()).resolves.toBe('fresh-access');
		expect(testState.saveSession).toHaveBeenCalledWith({
			access: 'fresh-access',
			refresh: 'refresh-token'
		});
	});

	it('clears storage and reactive state on sign-out', () => {
		const auth = new AuthState();
		auth.updateCurrentUser(currentUser);
		auth.signOut();
		expect(testState.clearSession).toHaveBeenCalledOnce();
		expect(auth.currentUser).toBeNull();
		expect(auth.status).toBe('signed-out');
	});

	it('reports unavailable without clearing storage after a non-auth load failure', async () => {
		testState.access = 'access-token';
		testState.getCurrentUser.mockRejectedValue(new Error('Offline'));
		const auth = new AuthState();
		await expect(auth.initialize()).resolves.toBeNull();
		expect(auth.status).toBe('unavailable');
		expect(testState.clearSession).not.toHaveBeenCalled();
	});

	it('clears an invalid persisted session without redirecting during initialization', async () => {
		testState.access = 'expired-access';
		testState.getCurrentUser.mockRejectedValue(new ApiRequestError(401, 'Unauthorized'));
		const auth = new AuthState();
		await expect(auth.initialize()).resolves.toBeNull();
		expect(auth.status).toBe('signed-out');
		expect(testState.clearSession).toHaveBeenCalledOnce();
	});
});
~~~

- [ ] **Step 2: Run the lifecycle test and verify it fails**

Run from web/:

~~~powershell
pnpm exec vitest run src/lib/auth/auth-state.test.ts
~~~

Expected: failure because the auth-state.svelte module does not exist.

- [ ] **Step 3: Implement the lifecycle class**

Create web/src/lib/auth/auth-state.svelte.ts:

~~~ts
import { browser } from '$app/environment';
import { getCurrentUser, refreshAccessToken, signIn as requestSignIn } from '$lib/api/auth';
import { ApiRequestError } from '$lib/api/client';
import type { CurrentUser } from '$lib/api/types';
import { clearSession, getAccessToken, getRefreshToken, saveSession } from '$lib/auth/session';

export type AuthStatus = 'idle' | 'loading' | 'signed-in' | 'signed-out' | 'unavailable';

export class AuthState {
	currentUser = $state<CurrentUser | null>(null);
	status = $state<AuthStatus>('idle');
	#initialization: Promise<CurrentUser | null> | null = null;

	async initialize(): Promise<CurrentUser | null> {
		if (!browser) return null;

		const accessToken = getAccessToken();
		if (!accessToken) {
			this.signOut();
			return null;
		}

		if (this.#initialization) return this.#initialization;

		this.status = 'loading';
		this.#initialization = getCurrentUser(accessToken)
			.then((user) => {
				this.currentUser = user;
				this.status = 'signed-in';
				return user;
			})
			.catch((cause: unknown) => {
				this.currentUser = null;
				if (this.isAuthenticationError(cause)) this.signOut();
				else this.status = 'unavailable';
				return null;
			})
			.finally(() => {
				this.#initialization = null;
			});

		return this.#initialization;
	}

	async signIn(email: string, password: string): Promise<CurrentUser | null> {
		if (!browser) return null;

		const tokens = await requestSignIn(email, password);
		saveSession(tokens);
		return this.initialize();
	}

	signOut(): void {
		clearSession();
		this.currentUser = null;
		this.status = 'signed-out';
	}

	async refreshSession(): Promise<string | null> {
		if (!browser) return null;

		const refreshToken = getRefreshToken();
		if (!refreshToken) {
			this.signOut();
			return null;
		}

		const { access } = await refreshAccessToken(refreshToken);
		saveSession({ access, refresh: refreshToken });
		return access;
	}

	updateCurrentUser(user: CurrentUser): void {
		this.currentUser = user;
		this.status = 'signed-in';
	}

	private isAuthenticationError(cause: unknown): boolean {
		return cause instanceof ApiRequestError && (cause.status === 401 || cause.status === 403);
	}
}

export const auth = new AuthState();
~~~

- [ ] **Step 4: Run the lifecycle test and verify it passes**

Run from web/:

~~~powershell
pnpm exec vitest run src/lib/auth/auth-state.test.ts
~~~

Expected: eight passing lifecycle tests.

- [ ] **Step 5: Commit the lifecycle deliverable**

~~~powershell
git add web/src/lib/auth/auth-state.svelte.ts web/src/lib/auth/auth-state.test.ts
git commit -m "feat: add reactive auth state lifecycle"
~~~

## Task 2: Add the redirecting authentication guard

**Files:**

- Modify: web/src/lib/auth/auth-state.svelte.ts
- Modify: web/src/lib/auth/auth-state.test.ts

**Interfaces:**

- Consumes: resolve from $app/paths, replaceInternalLocation from $lib/auth/navigation, and localizeInternalHref from $lib/navigation.
- Produces: requireAccessToken(): string | null and handleAuthenticationError(cause: unknown): boolean.
- A stored token is returned unchanged. With no token, the guard replaces the location with the localized sign-in route and encoded return URL.

- [ ] **Step 1: Extend the test boundary and write failing guard tests**

Add replaceLocation: vi.fn() to testState, reset it in beforeEach, and add these mocks before the dynamic AuthState import:

~~~ts
vi.mock('$app/paths', () => ({ resolve: (href: string) => href }));
vi.mock('$lib/auth/navigation', () => ({ replaceInternalLocation: testState.replaceLocation }));
vi.mock('$lib/navigation', () => ({ localizeInternalHref: (href: string) => href }));
~~~

In beforeEach, add this location stub:

~~~ts
vi.stubGlobal('window', {
	location: {
		pathname: '/account/profile',
		search: '?tab=security',
		hash: '#password'
	}
});
~~~

Append these tests:

~~~ts
describe('AuthState guard', () => {
	it('redirects a missing session with the complete attempted URL', () => {
		const auth = new AuthState();
		expect(auth.requireAccessToken()).toBeNull();
		expect(testState.replaceLocation).toHaveBeenCalledWith(
			'/auth/sign-in?redirectTo=%2Faccount%2Fprofile%3Ftab%3Dsecurity%23password'
		);
		expect(auth.status).toBe('signed-out');
	});

	it('returns an existing token without redirecting', () => {
		testState.access = 'access-token';
		const auth = new AuthState();
		expect(auth.requireAccessToken()).toBe('access-token');
		expect(testState.replaceLocation).not.toHaveBeenCalled();
	});

	it.each([401, 403])('clears and redirects for HTTP %i', (status) => {
		const auth = new AuthState();
		auth.updateCurrentUser(currentUser);
		expect(auth.handleAuthenticationError(new ApiRequestError(status, 'Denied'))).toBe(true);
		expect(testState.clearSession).toHaveBeenCalledOnce();
		expect(auth.currentUser).toBeNull();
		expect(testState.replaceLocation).toHaveBeenCalledWith(
			'/auth/sign-in?redirectTo=%2Faccount%2Fprofile%3Ftab%3Dsecurity%23password'
		);
	});

	it('leaves non-authentication errors for the page to render', () => {
		const auth = new AuthState();
		expect(auth.handleAuthenticationError(new ApiRequestError(500, 'Failure'))).toBe(false);
		expect(testState.clearSession).not.toHaveBeenCalled();
		expect(testState.replaceLocation).not.toHaveBeenCalled();
	});
});
~~~

- [ ] **Step 2: Run the focused test and verify it fails**

Run from web/:

~~~powershell
pnpm exec vitest run src/lib/auth/auth-state.test.ts
~~~

Expected: guard tests fail because requireAccessToken and handleAuthenticationError are not defined.

- [ ] **Step 3: Add the guard and centralized error handler**

Add these imports:

~~~ts
import { resolve } from '$app/paths';
import { replaceInternalLocation } from '$lib/auth/navigation';
import { localizeInternalHref } from '$lib/navigation';
~~~

Add these methods inside AuthState:

~~~ts
	requireAccessToken(): string | null {
		if (!browser) return null;

		const accessToken = getAccessToken();
		if (accessToken) return accessToken;

		this.signOut();
		this.redirectToSignIn();
		return null;
	}

	handleAuthenticationError(cause: unknown): boolean {
		if (!this.isAuthenticationError(cause)) return false;

		this.signOut();
		this.redirectToSignIn();
		return true;
	}

	private redirectToSignIn(): void {
		if (!browser) return;

		const currentHref =
			window.location.pathname + window.location.search + window.location.hash;
		const signInHref = resolve(localizeInternalHref('/auth/sign-in'));
		replaceInternalLocation(signInHref + '?redirectTo=' + encodeURIComponent(currentHref));
	}
~~~

- [ ] **Step 4: Run the focused test and verify it passes**

Run from web/:

~~~powershell
pnpm exec vitest run src/lib/auth/auth-state.test.ts
~~~

Expected: all lifecycle and guard tests pass.

- [ ] **Step 5: Run complete frontend verification**

Run from web/:

~~~powershell
pnpm exec vitest run
pnpm check
pnpm lint
~~~

Expected: each command exits with code 0 and reports no test, type, formatting, or lint failures.

- [ ] **Step 6: Commit the guard deliverable**

~~~powershell
git add web/src/lib/auth/auth-state.svelte.ts web/src/lib/auth/auth-state.test.ts
git commit -m "feat: add auth redirect guard"
~~~

## Final review checklist

- [ ] No component or route files changed.
- [ ] registerAccount remains a raw API function.
- [ ] All storage, networking, and redirect work remains browser-guarded.
- [ ] initialize() never redirects; the missing-token guard and HTTP 401/403 handler redirect.
- [ ] Focused tests, full unit tests, pnpm check, and pnpm lint have fresh passing output.
