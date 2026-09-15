import { requestJson } from './client';
import type {
	RegistrationPaymentSession,
	RegistrationRead,
	RegistrationSubmissionPayload
} from './types';

export function listRegistrations(accessToken: string) {
	return requestJson<RegistrationRead[]>('/registrations/', { accessToken });
}

export function getRegistration(accessToken: string, id: number) {
	return requestJson<RegistrationRead>(`/registrations/${id}/`, { accessToken });
}

export function submitRegistration(
	accessToken: string | null,
	payload: RegistrationSubmissionPayload,
	turnstileToken: string,
	proofFile?: File,
	reference?: string
) {
	const registration = { ...payload, turnstile_token: turnstileToken };
	let body: FormData | typeof registration = registration;
	if (proofFile) {
		body = new FormData();
		body.set('payload', JSON.stringify(registration));
		body.set('proof_file', proofFile);
		if (reference) body.set('reference', reference);
	}
	return requestJson<RegistrationRead>('/registrations/submit/', {
		method: 'POST',
		accessToken,
		body
	});
}

export function submitSavedRegistration(
	accessToken: string | null,
	payload: RegistrationSubmissionPayload,
	turnstileToken: string,
	credential: string
) {
	return requestJson<RegistrationRead>('/registrations/submit/', {
		method: 'POST',
		accessToken,
		headers: { 'X-Registration-Access': credential },
		body: { ...payload, turnstile_token: turnstileToken }
	});
}

export function resumeRegistration(credential: string) {
	return requestJson<RegistrationPaymentSession>('/registrations/resume/', {
		method: 'POST',
		headers: { 'X-Registration-Access': credential },
		body: {}
	});
}

export type RegistrationAccessOptions =
	{ accessToken: string; credential?: never } | { accessToken?: never; credential: string };

function privateSessionOptions(options: RegistrationAccessOptions) {
	return {
		accessToken: options.accessToken,
		headers: options.credential ? { 'X-Registration-Access': options.credential } : undefined
	};
}

export function getPaymentSession(id: number, options: RegistrationAccessOptions) {
	return requestJson<RegistrationPaymentSession>(`/registrations/${id}/payment-session/`, {
		method: 'POST',
		...privateSessionOptions(options),
		body: {}
	});
}

export function uploadPaymentProof(
	id: number,
	formData: FormData,
	options: RegistrationAccessOptions
) {
	return requestJson<RegistrationPaymentSession>(`/registrations/${id}/payment-proof/`, {
		method: 'POST',
		...privateSessionOptions(options),
		body: formData
	});
}

export function submitPaymentAttempt(
	accessToken: string,
	registrationId: number,
	formData: FormData,
	turnstileToken: string
) {
	formData.set('turnstile_token', turnstileToken);
	return requestJson<RegistrationRead['payment_attempts'][number]>(
		`/registrations/${registrationId}/payment-attempts/`,
		{ method: 'POST', accessToken, body: formData }
	);
}

export interface PaymentInstructions {
	token: string;
	transfer_content_template: string;
	transfer_content_limit: number;
	amount: string;
	currency: string;
}
export function reservePaymentInstructions(gameId: number, token?: string) {
	return requestJson<PaymentInstructions>('/payment-references/', {
		method: 'POST',
		body: { tournament_game: gameId, ...(token ? { token } : {}) }
	});
}
export function getPaymentInstructions(accessToken: string, registrationId: number) {
	return requestJson<{ transfer_content: string; transfer_content_limit: number }>(
		`/registrations/${registrationId}/payment-instructions/`,
		{
			method: 'POST',
			accessToken
		}
	);
}
