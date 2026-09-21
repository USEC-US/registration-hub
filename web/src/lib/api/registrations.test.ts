import { beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
import { requestJson } from './client';
import {
	getPaymentSession,
	resumeRegistration,
	submitPaymentAttempt,
	submitRegistration,
	submitSavedRegistration,
	uploadPaymentProof
} from './registrations';
import type {
	RegistrationPaymentSession,
	RegistrationRead,
	RegistrationSubmissionPayload
} from './types';

vi.mock('./client', () => ({ requestJson: vi.fn() }));

const payload: RegistrationSubmissionPayload = {
	tournament_game: 1,
	team_name: 'Team One',
	team_tag: 'ONE',
	submitter_role: 'captain',
	contact_facebook_snapshot: 'fb',
	contact_phone_snapshot: '123',
	members: []
};
const registration: RegistrationRead = {
	id: 73,
	tournament_game: {
		id: 1,
		tournament_name: 'USEC 2026',
		game_name: 'Valorant',
		main_roster_size: 5,
		substitute_limit: 2,
		fee_amount: '100000',
		fee_currency: 'VND'
	},
	team_name: 'Team One',
	team_tag: 'ONE',
	status: 'SUBMITTED',
	fee_amount_snapshot: '100000',
	fee_currency_snapshot: 'VND',
	submitted_at: '2026-09-15T01:00:00Z',
	payment_required: true,
	payment_reference: 'USEC-73',
	payment_state: 'UNPAID',
	payment_due_at: '2026-09-15T02:00:00Z',
	expired: false,
	members: [],
	status_events: [{ to_status: 'SUBMITTED', created_at: '2026-09-15T01:00:00Z' }],
	payment_attempts: []
};
const paymentSession: RegistrationPaymentSession = {
	tournament_slug: 'summer',
	registration,
	payment_state: 'UNPAID',
	payment_due_at: '2026-09-15T02:00:00Z',
	server_now: '2026-09-15T01:10:00Z',
	expired: false,
	can_upload_proof: true,
	can_retry_registration: false,
	replacement_note: '',
	saved_submission: payload,
	institution_labels: {},
	instructions: {
		bank_name: 'Example Bank',
		bank_bin: '970000',
		account_number: '000111222',
		account_holder: 'USEC ORGANIZER',
		amount: '100000',
		currency: 'VND',
		transfer_content: 'USEC-73',
		transfer_content_limit: 25,
		qr_payload: '000201...',
		qr_png_data_url: 'data:image/png;base64,AA==',
		qr_contains_transfer_content: true
	}
};

describe('registrations api', () => {
	beforeEach(() => {
		vi.mocked(requestJson).mockReset();
	});

	it('sends a turnstile token during registration submission', async () => {
		vi.mocked(requestJson).mockResolvedValue(registration);

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
			team_tag: '',
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

	it('submits the staged payload with its dedicated access credential', async () => {
		vi.mocked(requestJson).mockResolvedValue(registration);
		await submitSavedRegistration('account-token', payload, 'fresh-challenge', 'a'.repeat(64));
		expect(requestJson).toHaveBeenCalledWith('/registrations/submit/', {
			method: 'POST',
			accessToken: 'account-token',
			headers: { 'X-Registration-Access': 'a'.repeat(64) },
			body: { ...payload, turnstile_token: 'fresh-challenge' }
		});
	});

	it('routes credential-only resume and scoped payment session requests', async () => {
		vi.mocked(requestJson).mockResolvedValue(paymentSession);
		await resumeRegistration('b'.repeat(64));
		expect(requestJson).toHaveBeenNthCalledWith(1, '/registrations/resume/', {
			method: 'POST',
			headers: { 'X-Registration-Access': 'b'.repeat(64) },
			body: {}
		});
		await getPaymentSession(73, { accessToken: 'account-token' });
		expect(requestJson).toHaveBeenNthCalledWith(2, '/registrations/73/payment-session/', {
			method: 'POST',
			accessToken: 'account-token',
			headers: undefined,
			body: {}
		});
		await getPaymentSession(73, { credential: 'c'.repeat(64) });
		expect(requestJson).toHaveBeenNthCalledWith(3, '/registrations/73/payment-session/', {
			method: 'POST',
			accessToken: undefined,
			headers: { 'X-Registration-Access': 'c'.repeat(64) },
			body: {}
		});
	});

	it('uploads proof through the private endpoint without mutating caller form data', async () => {
		vi.mocked(requestJson).mockResolvedValue(paymentSession);
		const formData = new FormData();
		formData.set('proof_file', new File(['png'], 'proof.png', { type: 'image/png' }));
		await uploadPaymentProof(73, formData, { credential: 'd'.repeat(64) });
		expect(requestJson).toHaveBeenCalledWith('/registrations/73/payment-proof/', {
			method: 'POST',
			accessToken: undefined,
			headers: { 'X-Registration-Access': 'd'.repeat(64) },
			body: formData
		});
	});

	it('preserves normalized API errors from private recovery requests', async () => {
		const rejection = new Error('unknown credential');
		vi.mocked(requestJson).mockRejectedValue(rejection);
		await expect(resumeRegistration('e'.repeat(64))).rejects.toBe(rejection);
	});
});
