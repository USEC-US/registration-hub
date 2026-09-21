import { beforeEach, describe, expect, it, vi } from 'vitest';
import { requestJson } from './client';
import { clearSession, getAccessToken, saveSession } from '$lib/auth/session';

vi.mock('$app/environment', () => ({ browser: true, dev: true }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

const baseUrl = 'http://api.test';
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

describe('automatic token refresh', () => {
	it('does not send an old page token after another tab signs in as a different account', async () => {
		vi.resetModules();
		const otherTab = await import('$lib/auth/session');
		otherTab.saveSession({ access: 'other-account', refresh: 'other-refresh' });
		let requests = 0;
		const fetcher: typeof fetch = async () => {
			requests++;
			return json({}, 401);
		};
		await expect(
			requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' })
		).rejects.toMatchObject({ status: 409 });
		expect(requests).toBe(0);
		expect(getAccessToken()).toBe('other-account');
	});
	it('recognizes a token rotated by another tab', async () => {
		vi.resetModules();
		const otherTab = await import('$lib/auth/session');
		otherTab.rotateSession(
			{ access: 'fresh-in-other-tab', refresh: 'refresh' },
			otherTab.getSessionRevision(),
			'refresh'
		);
		const seen: string[] = [];
		const fetcher: typeof fetch = async (_url, init) => {
			const auth = new Headers(init?.headers).get('authorization')!;
			seen.push(auth);
			return auth === 'Bearer fresh-in-other-tab' ? json({ ok: true }) : json({}, 401);
		};
		await expect(
			requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' })
		).resolves.toEqual({ ok: true });
		expect(seen).toEqual(['Bearer fresh-in-other-tab']);
	});
	it.each([200, 401])(
		'discards a %i response if the session changes while its body is read',
		async (status) => {
			const fetcher: typeof fetch = async (url, init) => {
				if (String(url).endsWith('/auth/token/refresh/')) return json({ access: 'fresh' });
				if (new Headers(init?.headers).get('authorization') === 'Bearer expired')
					return json({}, 401);
				const response = json({ ok: true }, status);
				response.json = async () => {
					saveSession({ access: 'new-account', refresh: 'new-refresh' });
					return { ok: true };
				};
				return response;
			};
			await expect(
				requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' })
			).rejects.toMatchObject({ status: 409 });
			expect(getAccessToken()).toBe('new-account');
		}
	);
	it('shares one refresh across concurrent requests and replays their original bodies', async () => {
		let refreshes = 0;
		const bodies: unknown[] = [];
		const fetcher: typeof fetch = async (url, init) => {
			if (String(url).endsWith('/auth/token/refresh/')) {
				refreshes++;
				await new Promise((resolve) => setTimeout(resolve, 10));
				return json({ access: 'fresh' });
			}
			if (new Headers(init?.headers).get('authorization') === 'Bearer expired')
				return json({}, 401);
			bodies.push(init?.body);
			return json({ ok: true });
		};
		const proof = new FormData();
		proof.set('proof_file', new Blob(['image']), 'proof.png');
		const results = await Promise.all([
			requestJson('/registrations/', {
				baseUrl,
				fetcher,
				accessToken: 'expired',
				method: 'POST',
				body: { team: 'A' }
			}),
			requestJson('/payment/', {
				baseUrl,
				fetcher,
				accessToken: 'expired',
				method: 'POST',
				body: proof
			})
		]);
		expect(results).toEqual([{ ok: true }, { ok: true }]);
		expect(refreshes).toBe(1);
		expect(bodies).toEqual(['{"team":"A"}', proof]);
		expect(getAccessToken()).toBe('fresh');
	});

	it('does not refresh a forbidden request or retry it', async () => {
		let requests = 0;
		const fetcher: typeof fetch = async () => {
			requests++;
			return json({}, 403);
		};
		await expect(
			requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' })
		).rejects.toMatchObject({ status: 403 });
		expect(requests).toBe(1);
		expect(getAccessToken()).toBe('expired');
	});

	it('reuses the refreshed token for later requests from an already-mounted page', async () => {
		const seen: string[] = [];
		const fetcher: typeof fetch = async (url, init) => {
			if (String(url).endsWith('/auth/token/refresh/')) return json({ access: 'fresh' });
			const auth = new Headers(init?.headers).get('authorization')!;
			seen.push(auth);
			return auth === 'Bearer expired' ? json({}, 401) : json({ ok: true });
		};
		await requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' });
		await requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' });
		expect(seen).toEqual(['Bearer expired', 'Bearer fresh', 'Bearer fresh']);
	});

	it('does not retry a mutation with another account after a session switch', async () => {
		let requests = 0;
		const fetcher: typeof fetch = async (url) => {
			requests++;
			if (String(url).endsWith('/auth/token/refresh/')) {
				saveSession({ access: 'other-account', refresh: 'other-refresh' });
				return json({ access: 'fresh' });
			}
			return json({}, 401);
		};
		await expect(
			requestJson('/private/', {
				baseUrl,
				fetcher,
				accessToken: 'expired',
				method: 'POST',
				body: {}
			})
		).rejects.toMatchObject({ status: 409 });
		expect(requests).toBe(2);
		expect(getAccessToken()).toBe('other-account');
	});

	it('retries at most once when a refreshed access token is rejected', async () => {
		let requests = 0;
		const fetcher: typeof fetch = async (url) => {
			requests++;
			return String(url).endsWith('/auth/token/refresh/')
				? json({ access: 'fresh' })
				: json({}, 401);
		};
		await expect(
			requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' })
		).rejects.toMatchObject({ status: 401 });
		expect(requests).toBe(3);
	});

	it('preserves the session on refresh network failure', async () => {
		const fetcher: typeof fetch = async (url) => {
			if (String(url).endsWith('/auth/token/refresh/')) throw new TypeError('Offline');
			return json({}, 401);
		};
		await expect(
			requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' })
		).rejects.toThrow('Offline');
		expect(getAccessToken()).toBe('expired');
	});

	it('does not restore a session after logout while refresh is pending', async () => {
		const fetcher: typeof fetch = async (url) => {
			if (String(url).endsWith('/auth/token/refresh/')) {
				clearSession();
				return json({ access: 'fresh' });
			}
			return json({}, 401);
		};
		await expect(
			requestJson('/private/', { baseUrl, fetcher, accessToken: 'expired' })
		).rejects.toMatchObject({ status: 409 });
		expect(getAccessToken()).toBeNull();
	});
});
