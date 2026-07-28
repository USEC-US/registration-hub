import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '$lib/api/client';
import type { CurrentUser, TokenPair } from '$lib/api/types';
import { AuthState } from './auth-state.svelte';

const dependencies = vi.hoisted(() => ({
	accessToken: null as string | null,
	refreshToken: null as string | null,
	getCurrentUser: vi.fn(),
	requestSignIn: vi.fn(),
	refreshAccessToken: vi.fn(),
	saveSession: vi.fn(),
	clearSession: vi.fn(),
	replaceInternalLocation: vi.fn()
}));

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/api/auth', () => ({
	getCurrentUser: dependencies.getCurrentUser,
	signIn: dependencies.requestSignIn,
	refreshAccessToken: dependencies.refreshAccessToken
}));
vi.mock('$lib/auth/session', () => ({
	getAccessToken: () => dependencies.accessToken,
	getRefreshToken: () => dependencies.refreshToken,
	saveSession: (tokens: TokenPair) => {
		dependencies.saveSession(tokens);
		dependencies.accessToken = tokens.access;
		dependencies.refreshToken = tokens.refresh;
	},
	clearSession: () => {
		dependencies.clearSession();
		dependencies.accessToken = null;
		dependencies.refreshToken = null;
	}
}));
vi.mock('$lib/auth/navigation', () => ({
	replaceInternalLocation: dependencies.replaceInternalLocation
}));
vi.mock('$lib/navigation', () => ({
	localizeInternalHref: (href: string) => href
}));
vi.mock('$app/paths', () => ({ resolve: (href: string) => href }));

const currentUser: CurrentUser = {
	id: 7,
	email: 'player@example.com',
	first_name: 'Minh',
	last_name: 'Nguyen',
	school: 'HCMUS'
};

const newCurrentUser: CurrentUser = {
	id: 8,
	email: 'new@example.com',
	first_name: 'Lan',
	last_name: 'Tran',
	school: 'HCMUT'
};

beforeEach(() => {
	dependencies.accessToken = null;
	dependencies.refreshToken = null;
	dependencies.getCurrentUser.mockReset();
	dependencies.requestSignIn.mockReset();
	dependencies.refreshAccessToken.mockReset();
	dependencies.saveSession.mockClear();
	dependencies.clearSession.mockClear();
	dependencies.replaceInternalLocation.mockClear();
	vi.stubGlobal('window', {
		location: {
			pathname: '/account/profile',
			search: '?tab=security',
			hash: '#password'
		}
	});
});

describe('AuthState', () => {
	it('becomes signed out without requesting a user when no access token exists', async () => {
		const authState = new AuthState();

		await expect(authState.initialize()).resolves.toBeNull();

		expect(authState.status).toBe('signed-out');
		expect(authState.currentUser).toBeNull();
		expect(dependencies.getCurrentUser).not.toHaveBeenCalled();
	});

	it('hydrates the current user from the persisted access token', async () => {
		dependencies.accessToken = 'access-token';
		dependencies.getCurrentUser.mockResolvedValue(currentUser);
		const authState = new AuthState();

		await expect(authState.initialize()).resolves.toEqual(currentUser);

		expect(authState.status).toBe('signed-in');
		expect(authState.currentUser).toEqual(currentUser);
		expect(dependencies.getCurrentUser).toHaveBeenCalledWith('access-token');
	});

	it('shares a single in-flight current-user request', async () => {
		dependencies.accessToken = 'access-token';
		let resolveUser!: (user: CurrentUser) => void;
		dependencies.getCurrentUser.mockReturnValue(
			new Promise<CurrentUser>((resolve) => {
				resolveUser = resolve;
			})
		);
		const authState = new AuthState();

		const firstLoad = authState.initialize();
		const secondLoad = authState.initialize();
		resolveUser(currentUser);

		await expect(Promise.all([firstLoad, secondLoad])).resolves.toEqual([
			currentUser,
			currentUser
		]);
		expect(dependencies.getCurrentUser).toHaveBeenCalledTimes(1);
	});

	it('does not let an older hydration clear a session created by sign-in', async () => {
		dependencies.accessToken = 'old-access-token';
		let rejectOldHydration!: (reason: unknown) => void;
		dependencies.getCurrentUser
			.mockReturnValueOnce(
				new Promise<CurrentUser>((_, reject) => {
					rejectOldHydration = reject;
				})
			)
			.mockResolvedValueOnce(newCurrentUser);
		dependencies.requestSignIn.mockResolvedValue({
			access: 'new-access-token',
			refresh: 'new-refresh-token'
		});
		const authState = new AuthState();

		const oldInitialization = authState.initialize();
		const signIn = authState.signIn('new@example.com', 'password');
		await vi.waitFor(() =>
			expect(dependencies.getCurrentUser).toHaveBeenLastCalledWith('new-access-token')
		);
		rejectOldHydration(new ApiRequestError(401, 'Expired.'));

		await expect(signIn).resolves.toEqual(newCurrentUser);
		await expect(oldInitialization).resolves.toBeNull();
		expect(dependencies.accessToken).toBe('new-access-token');
		expect(dependencies.clearSession).not.toHaveBeenCalled();
		expect(authState.currentUser).toEqual(newCurrentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('persists credentials and hydrates the user when signing in', async () => {
		dependencies.requestSignIn.mockResolvedValue({
			access: 'new-access-token',
			refresh: 'new-refresh-token'
		});
		dependencies.getCurrentUser.mockResolvedValue(currentUser);
		const authState = new AuthState();

		await expect(authState.signIn('player@example.com', 'password')).resolves.toEqual(currentUser);

		expect(dependencies.saveSession).toHaveBeenCalledWith({
			access: 'new-access-token',
			refresh: 'new-refresh-token'
		});
		expect(authState.status).toBe('signed-in');
		expect(authState.currentUser).toEqual(currentUser);
	});

	it('retains the refresh token while replacing the access token', async () => {
		dependencies.accessToken = 'expired-access-token';
		dependencies.refreshToken = 'refresh-token';
		dependencies.refreshAccessToken.mockResolvedValue({ access: 'fresh-access-token' });
		const authState = new AuthState();

		await expect(authState.refreshSession()).resolves.toBe('fresh-access-token');

		expect(dependencies.saveSession).toHaveBeenCalledWith({
			access: 'fresh-access-token',
			refresh: 'refresh-token'
		});
	});

	it('clears storage and user state when signing out', () => {
		const authState = new AuthState();
		authState.updateCurrentUser(currentUser);

		authState.signOut();

		expect(dependencies.clearSession).toHaveBeenCalledOnce();
		expect(authState.status).toBe('signed-out');
		expect(authState.currentUser).toBeNull();
	});

	it('marks a non-authentication current-user error as unavailable without clearing the session', async () => {
		dependencies.accessToken = 'access-token';
		dependencies.getCurrentUser.mockRejectedValue(new Error('Network unavailable'));
		const authState = new AuthState();

		await expect(authState.initialize()).resolves.toBeNull();

		expect(authState.status).toBe('unavailable');
		expect(dependencies.clearSession).not.toHaveBeenCalled();
	});

	it('redirects an absent session to sign-in with the full attempted URL', () => {
		const authState = new AuthState();

		expect(authState.requireAccessToken()).toBeNull();

		expect(dependencies.replaceInternalLocation).toHaveBeenCalledWith(
			'/auth/sign-in?redirect=%2Faccount%2Fprofile%3Ftab%3Dsecurity%23password'
		);
		expect(authState.status).toBe('signed-out');
	});

	it.each([401, 403])('clears and redirects for an authentication error with status %i', (status) => {
		const authState = new AuthState();
		authState.updateCurrentUser(currentUser);

		expect(
			authState.handleAuthenticationError(new ApiRequestError(status, 'Authentication failed.'))
		).toBe(true);

		expect(dependencies.clearSession).toHaveBeenCalledOnce();
		expect(authState.currentUser).toBeNull();
		expect(dependencies.replaceInternalLocation).toHaveBeenCalledWith(
			'/auth/sign-in?redirect=%2Faccount%2Fprofile%3Ftab%3Dsecurity%23password'
		);
	});

	it('leaves non-authentication errors for the caller to render', () => {
		const authState = new AuthState();

		expect(authState.handleAuthenticationError(new ApiRequestError(500, 'Server error.'))).toBe(false);

		expect(dependencies.clearSession).not.toHaveBeenCalled();
		expect(dependencies.replaceInternalLocation).not.toHaveBeenCalled();
	});
});
