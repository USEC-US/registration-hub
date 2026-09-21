import { browser } from '$app/environment';
import type { TokenPair } from '$lib/api/types';

const ACCESS_TOKEN_KEY = 'usec.accessToken';
const REFRESH_TOKEN_KEY = 'usec.refreshToken';
const SESSION_ID_KEY = 'usec.sessionId';
const ROTATION_KEY = 'usec.tokenRotation';
let revision = 0;

export function getSessionRevision(): string {
	return `${revision}:${browser ? (localStorage.getItem(SESSION_ID_KEY) ?? '') : ''}`;
}

function previousTokens(current: string | null): string[] {
	if (!browser || !current) return [];
	try {
		const record = JSON.parse(localStorage.getItem(ROTATION_KEY) ?? 'null');
		return record?.access === current && Array.isArray(record.previous)
			? record.previous.filter((token: unknown): token is string => typeof token === 'string')
			: [];
	} catch {
		return [];
	}
}

export function isSessionAccessToken(token: string): boolean {
	const current = getAccessToken();
	return current === token || previousTokens(current).includes(token);
}

export function rotateSession(
	tokens: TokenPair,
	expectedRevision: string,
	expectedRefresh: string
): boolean {
	if (
		!browser ||
		getSessionRevision() !== expectedRevision ||
		getRefreshToken() !== expectedRefresh
	)
		return false;
	const previous = getAccessToken();
	const history = new Set(previousTokens(previous));
	if (previous) history.add(previous);
	// Persist rotation history so mounted forms in other tabs recognize their old token.
	localStorage.setItem(
		ROTATION_KEY,
		JSON.stringify({ access: tokens.access, previous: [...history] })
	);
	localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
	localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
	return true;
}

export function saveSession(tokens: TokenPair): void {
	if (!browser) return;
	revision++;
	localStorage.setItem(SESSION_ID_KEY, crypto.randomUUID());
	localStorage.removeItem(ROTATION_KEY);
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
	revision++;
	localStorage.removeItem(SESSION_ID_KEY);
	localStorage.removeItem(ROTATION_KEY);
	localStorage.removeItem(ACCESS_TOKEN_KEY);
	localStorage.removeItem(REFRESH_TOKEN_KEY);
}
