import { requestJson } from './client';
import type { RegistrationRead, RegistrationSubmissionPayload } from './types';

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

export interface PaymentReference {
	token: string;
	reference: string;
	amount: string;
	currency: string;
}
export function reservePaymentReference(gameId: number, token?: string) {
	return requestJson<PaymentReference>('/payment-references/', {
		method: 'POST',
		body: { tournament_game: gameId, ...(token ? { token } : {}) }
	});
}
export function getPaymentReference(accessToken: string, registrationId: number) {
	return requestJson<{ reference: string }>(`/registrations/${registrationId}/payment-reference/`, {
		method: 'POST',
		accessToken
	});
}
