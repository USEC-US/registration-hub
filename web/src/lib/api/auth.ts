import { requestJson } from './client';
import type { CurrentUser, InstitutionChoice, RegisterAccountPayload, TokenPair } from './types';

type AccountIdentityInput = {
	first_name: string;
	last_name: string;
} & InstitutionChoice;

export function registerAccount(payload: RegisterAccountPayload, turnstileToken?: string) {
	return requestJson<CurrentUser>('/auth/register/', {
		method: 'POST',
		body: { ...payload, turnstile_token: turnstileToken }
	});
}

export function signIn(email: string, password: string, turnstileToken?: string) {
	return requestJson<TokenPair>('/auth/token/', {
		method: 'POST',
		body: { email, password, turnstile_token: turnstileToken }
	});
}

export function refreshAccessToken(refresh: string) {
	return requestJson<Pick<TokenPair, 'access'>>('/auth/token/refresh/', {
		method: 'POST',
		body: { refresh }
	});
}

export function getCurrentUser(accessToken: string) {
	return requestJson<CurrentUser>('/account/me/', { accessToken });
}

export function updateCurrentUser(
	accessToken: string,
	payload: AccountIdentityInput
) {
	return requestJson<CurrentUser>('/account/me/', {
		method: 'PATCH',
		accessToken,
		body: payload
	});
}
