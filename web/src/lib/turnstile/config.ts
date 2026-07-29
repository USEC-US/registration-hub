import { dev } from '$app/environment';
import { env } from '$env/dynamic/public';

export type TurnstileAction =
	| 'sign-in'
	| 'account-register'
	| 'registration-submit'
	| 'payment-proof-submit';

export function getTurnstileSiteKey(): string {
	const siteKey = env.PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? '';
	if (!siteKey && !dev) {
		throw new Error('PUBLIC_TURNSTILE_SITE_KEY is required outside development.');
	}
	return siteKey;
}

export function hasTurnstileSiteKey(): boolean {
	return getTurnstileSiteKey().length > 0;
}
