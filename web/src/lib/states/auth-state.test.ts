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

		await expect(Promise.all([firstLoad, secondLoad])).resolves.toEqual([currentUser, currentUser]);
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

	it('does not let old hydration authentication failure cancel a pending sign-in', async () => {
		dependencies.accessToken = 'old-access-token';
		let rejectOldHydration!: (reason: unknown) => void;
		let resolveSignIn!: (tokens: TokenPair) => void;
		dependencies.getCurrentUser
			.mockReturnValueOnce(
				new Promise<CurrentUser>((_, reject) => {
					rejectOldHydration = reject;
				})
			)
			.mockResolvedValueOnce(newCurrentUser);
		dependencies.requestSignIn.mockReturnValue(
			new Promise<TokenPair>((resolve) => {
				resolveSignIn = resolve;
			})
		);
		const authState = new AuthState();

		const oldInitialization = authState.initialize();
		const signIn = authState.signIn('new@example.com', 'password');
		rejectOldHydration(new ApiRequestError(401, 'Expired.'));
		await expect(oldInitialization).resolves.toBeNull();
		resolveSignIn({
			access: 'new-access-token',
			refresh: 'new-refresh-token'
		});

		await expect(signIn).resolves.toEqual(newCurrentUser);
		expect(dependencies.clearSession).not.toHaveBeenCalled();
		expect(dependencies.accessToken).toBe('new-access-token');
		expect(dependencies.refreshToken).toBe('new-refresh-token');
		expect(authState.currentUser).toEqual(newCurrentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('resolves a successful hydration as null after its session is invalidated', async () => {
		dependencies.accessToken = 'access-token';
		let resolveHydration!: (user: CurrentUser) => void;
		dependencies.getCurrentUser.mockReturnValue(
			new Promise<CurrentUser>((resolve) => {
				resolveHydration = resolve;
			})
		);
		const authState = new AuthState();

		const initialization = authState.initialize();
		authState.signOut();
		resolveHydration(currentUser);

		await expect(initialization).resolves.toBeNull();
		expect(authState.currentUser).toBeNull();
		expect(authState.status).toBe('signed-out');
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

	it('does not commit a deferred sign-in after sign-out invalidates it', async () => {
		let resolveSignIn!: (tokens: TokenPair) => void;
		dependencies.requestSignIn.mockReturnValue(
			new Promise<TokenPair>((resolve) => {
				resolveSignIn = resolve;
			})
		);
		dependencies.getCurrentUser.mockResolvedValue(currentUser);
		const authState = new AuthState();

		const signIn = authState.signIn('player@example.com', 'password');
		authState.signOut();
		resolveSignIn({
			access: 'late-access-token',
			refresh: 'late-refresh-token'
		});

		await expect(signIn).resolves.toBeNull();
		expect(dependencies.saveSession).not.toHaveBeenCalled();
		expect(dependencies.accessToken).toBeNull();
		expect(dependencies.refreshToken).toBeNull();
		expect(dependencies.getCurrentUser).not.toHaveBeenCalled();
		expect(authState.currentUser).toBeNull();
		expect(authState.status).toBe('signed-out');
	});

	it('resolves a rejected deferred sign-in as null after sign-out invalidates it', async () => {
		let rejectSignIn!: (reason: unknown) => void;
		dependencies.requestSignIn.mockReturnValue(
			new Promise<TokenPair>((_, reject) => {
				rejectSignIn = reject;
			})
		);
		const authState = new AuthState();

		const signIn = authState.signIn('player@example.com', 'password');
		authState.signOut();
		rejectSignIn(new ApiRequestError(401, 'Invalid credentials.'));

		await expect(signIn).resolves.toBeNull();
		expect(dependencies.saveSession).not.toHaveBeenCalled();
		expect(dependencies.accessToken).toBeNull();
		expect(dependencies.refreshToken).toBeNull();
		expect(authState.currentUser).toBeNull();
		expect(authState.status).toBe('signed-out');
	});

	it('lets only the newest overlapping sign-in commit its session', async () => {
		let resolveFirstSignIn!: (tokens: TokenPair) => void;
		let resolveSecondSignIn!: (tokens: TokenPair) => void;
		dependencies.requestSignIn
			.mockReturnValueOnce(
				new Promise<TokenPair>((resolve) => {
					resolveFirstSignIn = resolve;
				})
			)
			.mockReturnValueOnce(
				new Promise<TokenPair>((resolve) => {
					resolveSecondSignIn = resolve;
				})
			);
		dependencies.getCurrentUser
			.mockResolvedValueOnce(newCurrentUser)
			.mockResolvedValueOnce(currentUser);
		const authState = new AuthState();

		const firstSignIn = authState.signIn('first@example.com', 'password');
		const secondSignIn = authState.signIn('new@example.com', 'password');
		resolveSecondSignIn({
			access: 'new-access-token',
			refresh: 'new-refresh-token'
		});
		await expect(secondSignIn).resolves.toEqual(newCurrentUser);
		resolveFirstSignIn({
			access: 'old-access-token',
			refresh: 'old-refresh-token'
		});

		await expect(firstSignIn).resolves.toBeNull();
		expect(dependencies.saveSession).toHaveBeenCalledOnce();
		expect(dependencies.accessToken).toBe('new-access-token');
		expect(dependencies.refreshToken).toBe('new-refresh-token');
		expect(dependencies.getCurrentUser).toHaveBeenCalledOnce();
		expect(authState.currentUser).toEqual(newCurrentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('preserves old-session hydration when the active sign-in request fails', async () => {
		dependencies.accessToken = 'old-access-token';
		let resolveOldHydration!: (user: CurrentUser) => void;
		dependencies.getCurrentUser
			.mockReturnValueOnce(
				new Promise<CurrentUser>((resolve) => {
					resolveOldHydration = resolve;
				})
			)
			.mockResolvedValueOnce(currentUser);
		const signInError = new ApiRequestError(401, 'Invalid credentials.');
		dependencies.requestSignIn.mockRejectedValue(signInError);
		const authState = new AuthState();

		const oldInitialization = authState.initialize();
		await expect(authState.signIn('player@example.com', 'password')).rejects.toBe(signInError);
		resolveOldHydration(currentUser);

		await expect(oldInitialization).resolves.toBeNull();
		await vi.waitFor(() => expect(authState.currentUser).toEqual(currentUser));
		expect(dependencies.getCurrentUser).toHaveBeenCalledTimes(2);
		expect(dependencies.accessToken).toBe('old-access-token');
		expect(dependencies.saveSession).not.toHaveBeenCalled();
		expect(authState.currentUser).toEqual(currentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('retains the refresh token while replacing the access token', async () => {
		dependencies.accessToken = 'expired-access-token';
		dependencies.refreshToken = 'refresh-token';
		dependencies.refreshAccessToken.mockResolvedValue({ access: 'fresh-access-token' });
		dependencies.getCurrentUser.mockResolvedValue(currentUser);
		const authState = new AuthState();

		await expect(authState.refreshSession()).resolves.toBe('fresh-access-token');

		expect(dependencies.saveSession).toHaveBeenCalledWith({
			access: 'fresh-access-token',
			refresh: 'refresh-token'
		});
	});

	it('hydrates the refreshed session when refresh replaces an in-flight initialization', async () => {
		dependencies.accessToken = 'expired-access-token';
		dependencies.refreshToken = 'refresh-token';
		let resolveOldHydration!: (user: CurrentUser) => void;
		dependencies.getCurrentUser
			.mockReturnValueOnce(
				new Promise<CurrentUser>((resolve) => {
					resolveOldHydration = resolve;
				})
			)
			.mockResolvedValueOnce(newCurrentUser);
		dependencies.refreshAccessToken.mockResolvedValue({ access: 'fresh-access-token' });
		const authState = new AuthState();

		const oldInitialization = authState.initialize();
		const refresh = authState.refreshSession();
		await vi.waitFor(() =>
			expect(dependencies.getCurrentUser).toHaveBeenLastCalledWith('fresh-access-token')
		);
		resolveOldHydration(currentUser);

		await expect(refresh).resolves.toBe('fresh-access-token');
		await expect(oldInitialization).resolves.toBeNull();
		expect(authState.currentUser).toEqual(newCurrentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('does not let old hydration authentication failure cancel a pending refresh', async () => {
		dependencies.accessToken = 'expired-access-token';
		dependencies.refreshToken = 'refresh-token';
		let rejectOldHydration!: (reason: unknown) => void;
		let resolveRefresh!: (tokens: { access: string }) => void;
		dependencies.getCurrentUser
			.mockReturnValueOnce(
				new Promise<CurrentUser>((_, reject) => {
					rejectOldHydration = reject;
				})
			)
			.mockResolvedValueOnce(newCurrentUser);
		dependencies.refreshAccessToken.mockReturnValue(
			new Promise<{ access: string }>((resolve) => {
				resolveRefresh = resolve;
			})
		);
		const authState = new AuthState();

		const oldInitialization = authState.initialize();
		const refresh = authState.refreshSession();
		rejectOldHydration(new ApiRequestError(401, 'Expired.'));
		await expect(oldInitialization).resolves.toBeNull();
		resolveRefresh({ access: 'fresh-access-token' });

		await expect(refresh).resolves.toBe('fresh-access-token');
		expect(dependencies.clearSession).not.toHaveBeenCalled();
		expect(dependencies.accessToken).toBe('fresh-access-token');
		expect(dependencies.refreshToken).toBe('refresh-token');
		expect(authState.currentUser).toEqual(newCurrentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('preserves old-session hydration when the active refresh request fails', async () => {
		dependencies.accessToken = 'old-access-token';
		dependencies.refreshToken = 'refresh-token';
		let resolveOldHydration!: (user: CurrentUser) => void;
		dependencies.getCurrentUser
			.mockReturnValueOnce(
				new Promise<CurrentUser>((resolve) => {
					resolveOldHydration = resolve;
				})
			)
			.mockResolvedValueOnce(currentUser);
		const refreshError = new ApiRequestError(401, 'Refresh failed.');
		dependencies.refreshAccessToken.mockRejectedValue(refreshError);
		const authState = new AuthState();

		const oldInitialization = authState.initialize();
		await expect(authState.refreshSession()).rejects.toBe(refreshError);
		resolveOldHydration(currentUser);

		await expect(oldInitialization).resolves.toBeNull();
		await vi.waitFor(() => expect(authState.currentUser).toEqual(currentUser));
		expect(dependencies.getCurrentUser).toHaveBeenCalledTimes(2);
		expect(dependencies.accessToken).toBe('old-access-token');
		expect(dependencies.saveSession).not.toHaveBeenCalled();
		expect(authState.currentUser).toEqual(currentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('does not let a deferred refresh overwrite a newer sign-in', async () => {
		dependencies.accessToken = 'expired-access-token';
		dependencies.refreshToken = 'old-refresh-token';
		let resolveRefresh!: (tokens: { access: string }) => void;
		dependencies.refreshAccessToken.mockReturnValue(
			new Promise<{ access: string }>((resolve) => {
				resolveRefresh = resolve;
			})
		);
		dependencies.requestSignIn.mockResolvedValue({
			access: 'new-access-token',
			refresh: 'new-refresh-token'
		});
		dependencies.getCurrentUser
			.mockResolvedValueOnce(newCurrentUser)
			.mockResolvedValueOnce(currentUser);
		const authState = new AuthState();

		const refresh = authState.refreshSession();
		await expect(authState.signIn('new@example.com', 'password')).resolves.toEqual(newCurrentUser);
		resolveRefresh({ access: 'stale-refreshed-access-token' });

		await expect(refresh).resolves.toBeNull();
		expect(dependencies.saveSession).toHaveBeenCalledOnce();
		expect(dependencies.accessToken).toBe('new-access-token');
		expect(dependencies.refreshToken).toBe('new-refresh-token');
		expect(dependencies.getCurrentUser).toHaveBeenCalledOnce();
		expect(authState.currentUser).toEqual(newCurrentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('resolves a rejected deferred refresh as null after a newer sign-in', async () => {
		dependencies.accessToken = 'expired-access-token';
		dependencies.refreshToken = 'old-refresh-token';
		let rejectRefresh!: (reason: unknown) => void;
		dependencies.refreshAccessToken.mockReturnValue(
			new Promise<{ access: string }>((_, reject) => {
				rejectRefresh = reject;
			})
		);
		dependencies.requestSignIn.mockResolvedValue({
			access: 'new-access-token',
			refresh: 'new-refresh-token'
		});
		dependencies.getCurrentUser.mockResolvedValue(newCurrentUser);
		const authState = new AuthState();

		const refresh = authState.refreshSession();
		await expect(authState.signIn('new@example.com', 'password')).resolves.toEqual(newCurrentUser);
		rejectRefresh(new ApiRequestError(401, 'Refresh failed.'));

		await expect(refresh).resolves.toBeNull();
		expect(dependencies.saveSession).toHaveBeenCalledOnce();
		expect(dependencies.accessToken).toBe('new-access-token');
		expect(dependencies.refreshToken).toBe('new-refresh-token');
		expect(authState.currentUser).toEqual(newCurrentUser);
		expect(authState.status).toBe('signed-in');
	});

	it('clears storage and user state when signing out', () => {
		dependencies.accessToken = 'access-token';
		const authState = new AuthState();
		const snapshot = authState.requireSessionSnapshot();
		authState.updateCurrentUser(snapshot!, currentUser);

		authState.signOut();

		expect(dependencies.clearSession).toHaveBeenCalledOnce();
		expect(authState.status).toBe('signed-out');
		expect(authState.currentUser).toBeNull();
	});

	it('updates shared user state only while a session snapshot remains current', () => {
		dependencies.accessToken = 'access-token';
		const authState = new AuthState();
		const snapshot = authState.requireSessionSnapshot();

		expect(snapshot).toEqual({ accessToken: 'access-token', generation: 0 });
		expect(authState.isSessionSnapshotCurrent(snapshot!)).toBe(true);
		expect(authState.updateCurrentUser(snapshot!, currentUser)).toBe(true);
		expect(authState.currentUser).toEqual(currentUser);
		expect(authState.status).toBe('signed-in');

		authState.signOut();

		expect(authState.isSessionSnapshotCurrent(snapshot!)).toBe(false);
		expect(authState.updateCurrentUser(snapshot!, newCurrentUser)).toBe(false);
		expect(authState.currentUser).toBeNull();
		expect(authState.status).toBe('signed-out');
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

	it.each([401, 403])(
		'clears and redirects for an authentication error with status %i',
		(status) => {
			dependencies.accessToken = 'access-token';
			const authState = new AuthState();
			const snapshot = authState.requireSessionSnapshot();
			authState.updateCurrentUser(snapshot!, currentUser);

			expect(
				authState.handleAuthenticationError(new ApiRequestError(status, 'Authentication failed.'))
			).toBe(true);

			expect(dependencies.clearSession).toHaveBeenCalledOnce();
			expect(authState.currentUser).toBeNull();
			expect(dependencies.replaceInternalLocation).toHaveBeenCalledWith(
				'/auth/sign-in?redirect=%2Faccount%2Fprofile%3Ftab%3Dsecurity%23password'
			);
		}
	);

	it('leaves non-authentication errors for the caller to render', () => {
		const authState = new AuthState();

		expect(authState.handleAuthenticationError(new ApiRequestError(500, 'Server error.'))).toBe(
			false
		);

		expect(dependencies.clearSession).not.toHaveBeenCalled();
		expect(dependencies.replaceInternalLocation).not.toHaveBeenCalled();
	});
});
