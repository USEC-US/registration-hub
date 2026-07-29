import { beforeEach, describe, expect, it, vi } from 'vitest';
import { requestJson } from './client';
import { submitPaymentAttempt, submitRegistration } from './registrations';
import type { RegistrationRead, RegistrationSubmissionPayload } from './types';

vi.mock('./client', () => ({ requestJson: vi.fn() }));

describe('registrations api', () => {
	beforeEach(() => {
		vi.mocked(requestJson).mockReset();
	});

	it('sends a turnstile token during registration submission', async () => {
		const payload: RegistrationSubmissionPayload = {
			tournament_game: 1,
			team_name: 'Team One',
			members: []
		};
		vi.mocked(requestJson).mockResolvedValue({} as RegistrationRead);

		await submitRegistration('access-token', payload, 'turnstile-token');

		expect(requestJson).toHaveBeenCalledWith('/registrations/submit/', {
			method: 'POST',
			accessToken: 'access-token',
			body: { ...payload, turnstile_token: 'turnstile-token' }
		});
	});

	it('adds a turnstile token to payment uploads', async () => {
		const formData = new FormData();
		formData.set('reference', 'bank-transfer-12');
		vi.mocked(requestJson).mockResolvedValue({} as RegistrationRead['payment_attempts'][number]);

		await submitPaymentAttempt('access-token', 34, formData, 'turnstile-token');

		expect(formData.get('turnstile_token')).toBe('turnstile-token');
		expect(requestJson).toHaveBeenCalledWith('/registrations/34/payment-attempts/', {
			method: 'POST',
			accessToken: 'access-token',
			body: formData
		});
	});
});
