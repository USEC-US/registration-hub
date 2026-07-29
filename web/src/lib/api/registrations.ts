import { requestJson } from './client';
import type { RegistrationRead, RegistrationSubmissionPayload } from './types';

export function listRegistrations(accessToken: string) {
	return requestJson<RegistrationRead[]>('/registrations/', { accessToken });
}

export function getRegistration(accessToken: string, id: number) {
	return requestJson<RegistrationRead>(`/registrations/${id}/`, { accessToken });
}

export function submitRegistration(
	accessToken: string,
	payload: RegistrationSubmissionPayload,
	turnstileToken: string
) {
	return requestJson<RegistrationRead>('/registrations/submit/', {
		method: 'POST',
		accessToken,
		body: { ...payload, turnstile_token: turnstileToken }
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
