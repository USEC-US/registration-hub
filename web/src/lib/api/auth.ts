import { requestJson } from './client';
import type { CurrentUser, TokenPair } from './types';

export function registerAccount(payload: {
	email: string;
	password: string;
	gamer_tag?: string;
	school?: string;
}) {
	return requestJson<CurrentUser>('/auth/register/', { method: 'POST', body: payload });
}

export function signIn(email: string, password: string) {
	return requestJson<TokenPair>('/auth/token/', { method: 'POST', body: { email, password } });
}

export function getCurrentUser(accessToken: string) {
	return requestJson<CurrentUser>('/account/me/', { accessToken });
}

export function updateCurrentUser(
	accessToken: string,
	payload: Pick<CurrentUser, 'gamer_tag' | 'school'>
) {
	return requestJson<CurrentUser>('/account/me/', {
		method: 'PATCH',
		accessToken,
		body: payload
	});
}
