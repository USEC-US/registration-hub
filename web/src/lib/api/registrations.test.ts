import { beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
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
			submitter_role: 'captain',
			contact_facebook_snapshot: 'fb',
			contact_phone_snapshot: '123',
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

	it('sends guest proof and the complete payload in one multipart submission', async () => {
		const payload = {
			tournament_game: 1,
			team_name: '',
			submitter_role: 'captain' as const,
			contact_facebook_snapshot: 'fb',
			contact_phone_snapshot: '123',
			members: []
		};
		const proof = new File(['image'], 'proof.png', { type: 'image/png' });
		await submitRegistration(null, payload, 'challenge', proof, 'transfer');
		const [, options] = vi.mocked(requestJson).mock.calls[0];
		expect(options?.accessToken).toBeNull();
		const body = options?.body as FormData;
		expect(body).toBeInstanceOf(FormData);
		expect(JSON.parse(String(body.get('payload')))).toEqual({
			...payload,
			turnstile_token: 'challenge'
		});
		expect(body.get('proof_file')).toBe(proof);
		expect(body.get('reference')).toBe('transfer');
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

	it('requires Turnstile tokens for protected registration requests', () => {
		expectTypeOf(submitRegistration).parameters.toEqualTypeOf<
			[
				accessToken: string | null,
				payload: RegistrationSubmissionPayload,
				turnstileToken: string,
				proofFile?: File,
				reference?: string
			]
		>();
		expectTypeOf(submitPaymentAttempt).parameters.toEqualTypeOf<
			[accessToken: string, registrationId: number, formData: FormData, turnstileToken: string]
		>();
		expect(submitRegistration).toBeTypeOf('function');
	});
});
