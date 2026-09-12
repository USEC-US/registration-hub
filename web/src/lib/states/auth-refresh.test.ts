import { beforeEach, expect, it, vi } from 'vitest';
import { AuthState } from './auth-state.svelte';
import { getAccessToken, saveSession } from '$lib/auth/session';
import { updateCurrentUser } from '$lib/api/auth';

vi.mock('$app/environment', () => ({ browser: true, dev: true }));
vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE_URL: 'http://api.test' } }));
vi.mock('$lib/navigation', () => ({ localizeInternalHref: (href: string) => href }));
vi.mock('$app/paths', () => ({ resolve: (href: string) => href }));
vi.mock('$lib/auth/navigation', () => ({ replaceInternalLocation: vi.fn() }));

const user = {
	id: 1,
	email: 'player@example.com',
	first_name: 'Player',
	last_name: 'One',
	institution: null
};
const json = (body: object, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
	const values = new Map<string, string>();
	vi.stubGlobal('localStorage', {
		getItem: (key: string) => values.get(key) ?? null,
		setItem: (key: string, value: string) => values.set(key, value),
		removeItem: (key: string) => values.delete(key)
	});
	saveSession({ access: 'expired', refresh: 'refresh' });
});

it('hydrates the signed-in user after automatic refresh', async () => {
	vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
		if (url.endsWith('/auth/token/refresh/')) return json({ access: 'fresh' });
		return new Headers(init.headers).get('authorization') === 'Bearer expired'
			? json({}, 401)
			: json(user);
	});
	const auth = new AuthState();
	await expect(auth.initialize()).resolves.toEqual(user);
	expect(auth.status).toBe('signed-in');
	expect(auth.currentUser).toEqual(user);
});

it('keeps a profile save snapshot valid across automatic refresh', async () => {
	vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
		if (url.endsWith('/auth/token/refresh/')) return json({ access: 'fresh' });
		return new Headers(init.headers).get('authorization') === 'Bearer expired'
			? json({}, 401)
			: json(user);
	});
	const auth = new AuthState();
	const snapshot = auth.requireSessionSnapshot()!;
	const saved = await updateCurrentUser(snapshot.accessToken, {
		first_name: 'Player',
		last_name: 'One',
		institution_label: 'School'
	});
	expect(auth.updateCurrentUser(snapshot, saved)).toBe(true);
	expect(auth.currentUser).toEqual(user);
});

it('signs out when refresh credentials are rejected', async () => {
	vi.stubGlobal('fetch', async () => json({}, 401));
	const auth = new AuthState();
	await expect(auth.initialize()).resolves.toBeNull();
	expect(auth.status).toBe('signed-out');
	expect(getAccessToken()).toBeNull();
});

it('preserves credentials when the refresh service is unavailable', async () => {
	vi.stubGlobal('fetch', async (url: string) =>
		json({}, url.endsWith('/auth/token/refresh/') ? 503 : 401)
	);
	const auth = new AuthState();
	await expect(auth.initialize()).resolves.toBeNull();
	expect(auth.status).toBe('unavailable');
	expect(getAccessToken()).toBe('expired');
});
