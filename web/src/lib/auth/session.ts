import { browser } from '$app/environment';
import type { TokenPair } from '$lib/api/types';

const ACCESS_TOKEN_KEY = 'usec.accessToken';
const REFRESH_TOKEN_KEY = 'usec.refreshToken';

export function saveSession(tokens: TokenPair): void {
	if (!browser) return;
	localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
	localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
}

export function getAccessToken(): string | null {
	if (!browser) return null;
	return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
	if (!browser) return null;
	return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function clearSession(): void {
	if (!browser) return;
	localStorage.removeItem(ACCESS_TOKEN_KEY);
	localStorage.removeItem(REFRESH_TOKEN_KEY);
}
