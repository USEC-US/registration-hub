import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearSession, getAccessToken, getRefreshToken, saveSession } from './session';

vi.mock('$app/environment', () => ({ browser: true }));

describe('session storage', () => {
	const store = new Map<string, string>();

	beforeEach(() => {
		store.clear();
		vi.stubGlobal('localStorage', {
			getItem: (key: string) => store.get(key) ?? null,
			setItem: (key: string, value: string) => store.set(key, value),
			removeItem: (key: string) => store.delete(key),
			clear: () => store.clear()
		});
	});

	it('saves and clears jwt tokens', () => {
		saveSession({ access: 'access-token', refresh: 'refresh-token' });

		expect(getAccessToken()).toBe('access-token');
		expect(getRefreshToken()).toBe('refresh-token');

		clearSession();

		expect(getAccessToken()).toBeNull();
		expect(getRefreshToken()).toBeNull();
	});
});
