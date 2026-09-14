import { ApiRequestError } from '$lib/api/client';
import type {
	RegistrationPaymentSession,
	RegistrationRead,
	RegistrationSubmissionPayload
} from '$lib/api/types';
import { describe, expect, it, vi } from 'vitest';
import {
	listAccess,
	type PendingSavedRegistrationAccess,
	type SavedRegistrationAccess
} from './browser-storage';
import { recoverRegistrationAttempt, submitRegistrationAttempt } from './submission';

class MemoryStorage implements Storage {
	private values = new Map<string, string>();
	get length() {
		return this.values.size;
	}
	clear() {
		this.values.clear();
	}
	getItem(key: string) {
		return this.values.get(key) ?? null;
	}
	key(index: number) {
		return [...this.values.keys()][index] ?? null;
	}
	removeItem(key: string) {
		this.values.delete(key);
	}
	setItem(key: string, value: string) {
		this.values.set(key, value);
	}
}

const credential = 'a'.repeat(64);
const payload: RegistrationSubmissionPayload = {
	tournament_game: 9,
	team_name: 'Saigon Sentinels',
	team_tag: 'SGS',
	submitter_role: 'captain',
	contact_facebook_snapshot: 'facebook.com/captain',
	contact_phone_snapshot: '0909000111',
	members: [
		{
			first_name_snapshot: 'An',
			last_name_snapshot: 'Nguyen',
			date_of_birth_snapshot: '2005-04-03',
			student_id_snapshot: 'SV123',
			gamer_tag_snapshot: 'Player One',
			institution_id: 12,
			is_captain: true,
			roster_role: 'main',
			display_order: 0
		}
	]
};
const registration: RegistrationRead = {
	id: 41,
	tournament_game: {
		id: 9,
		tournament_name: 'USEC 2026',
		game_name: 'Valorant',
		main_roster_size: 5,
		substitute_limit: 2,
		fee_amount: '100000',
		fee_currency: 'VND'
	},
	team_name: 'Saigon Sentinels',
	team_tag: 'SGS',
	status: 'SUBMITTED',
	fee_amount_snapshot: '100000',
	fee_currency_snapshot: 'VND',
	submitted_at: '2026-09-15T01:00:00Z',
	payment_required: true,
	payment_reference: 'USEC-41',
	payment_state: 'UNPAID',
	payment_due_at: '2026-09-15T02:00:00Z',
	expired: false,
	members: [
		{
			gamer_tag_snapshot: 'Player One',
			school_snapshot: 'University of Science',
			is_captain: true,
			roster_role: 'main',
			display_order: 0
		}
	],
	status_events: [{ to_status: 'SUBMITTED', created_at: '2026-09-15T01:00:00Z' }],
	payment_attempts: []
};
const session: RegistrationPaymentSession = {
	registration,
	payment_state: 'UNPAID',
	payment_due_at: '2026-09-15T02:00:00Z',
	server_now: '2026-09-15T01:10:00Z',
	expired: false,
	can_upload_proof: true,
	can_retry_registration: false,
	replacement_note: '',
	saved_submission: payload,
	institution_labels: { '0': 'University of Science' },
	instructions: {
		bank_name: 'Example Bank',
		bank_bin: '970000',
		account_number: '000111222',
		account_holder: 'USEC ORGANIZER',
		amount: '100000',
		currency: 'VND',
		transfer_content: 'USEC-41',
		transfer_content_limit: 25,
		qr_payload: '000201...',
		qr_png_data_url: 'data:image/png;base64,AA==',
		qr_contains_transfer_content: true
	}
};

function unresolved(state: 'prepared' | 'uncertain' = 'uncertain'): PendingSavedRegistrationAccess {
	return {
		version: 1,
		gameId: 9,
		credential,
		attemptState: state,
		registrationId: null,
		actorId: 7,
		submittedPayload: payload
	};
}

describe('saved registration submission recovery', () => {
	it('rejects a non-positive actor marker before storing or submitting', async () => {
		const storage = new MemoryStorage();
		const submit = vi.fn();
		const result = await submitRegistrationAttempt({
			storage,
			actorId: 0,
			accessToken: 'account-token',
			payload,
			turnstileToken: 'challenge',
			credentialFactory: () => credential,
			submit
		});
		expect(result).toMatchObject({ status: 'invalid-actor', credential });
		expect(listAccess(storage, 9)).toEqual([]);
		expect(submit).not.toHaveBeenCalled();
	});

	it('stores exact attempted fields before submitting and replaces personal data after success', async () => {
		const storage = new MemoryStorage();
		let observedBeforeRequest: SavedRegistrationAccess[] = [];
		const submit = vi.fn(async () => {
			observedBeforeRequest = listAccess(storage, 9);
			return registration;
		});

		const result = await submitRegistrationAttempt({
			storage,
			actorId: 7,
			accessToken: 'account-token',
			payload,
			turnstileToken: 'challenge',
			credentialFactory: () => credential,
			submit
		});

		expect(observedBeforeRequest).toEqual([unresolved('prepared')]);
		expect(result).toMatchObject({ status: 'submitted', registration, credential });
		expect(listAccess(storage, 9)).toEqual([
			{ version: 1, gameId: 9, credential, attemptState: 'submitted', registrationId: 41 }
		]);
	});

	it('marks a transport failure uncertain and resumes it without requiring account auth', async () => {
		const storage = new MemoryStorage();
		const submit = vi.fn().mockRejectedValue(new TypeError('network disconnected'));
		const first = await submitRegistrationAttempt({
			storage,
			actorId: 7,
			accessToken: 'account-token',
			payload,
			turnstileToken: 'challenge',
			credentialFactory: () => credential,
			submit
		});
		expect(first).toMatchObject({ status: 'uncertain', credential });
		expect(listAccess(storage, 9)).toEqual([unresolved('uncertain')]);

		const recovered = await recoverRegistrationAttempt({
			storage,
			entry: unresolved(),
			currentActorId: null,
			accessToken: null,
			turnstileToken: null,
			resume: async () => session,
			submit
		});
		expect(recovered).toMatchObject({ status: 'submitted', session, credential });
		expect(submit).toHaveBeenCalledOnce();
	});

	it('resumes first, then retries an unknown credential with the original key, payload, and actor', async () => {
		const storage = new MemoryStorage();
		const entry = unresolved();
		const resume = vi.fn().mockRejectedValue(new ApiRequestError(404, 'Not found'));
		const submit = vi.fn().mockResolvedValue(registration);
		const result = await recoverRegistrationAttempt({
			storage,
			entry,
			currentActorId: 7,
			accessToken: 'account-token',
			turnstileToken: 'fresh-challenge',
			resume,
			submit
		});

		expect(result).toMatchObject({ status: 'submitted', credential });
		expect(submit).toHaveBeenCalledWith('account-token', payload, 'fresh-challenge', credential);
	});

	it('requires the original account before replay and preserves the unresolved record', async () => {
		const storage = new MemoryStorage();
		const entry = unresolved();
		const submit = vi.fn();
		const result = await recoverRegistrationAttempt({
			storage,
			entry,
			currentActorId: null,
			accessToken: null,
			turnstileToken: 'fresh',
			resume: async () => {
				throw new ApiRequestError(404, 'Not found');
			},
			submit
		});
		expect(result).toMatchObject({ status: 'account-session-required', credential });
		expect(submit).not.toHaveBeenCalled();
		expect(listAccess(storage, 9)).toEqual([entry]);
	});

	it('allows editing after a definite first-attempt validation rejection', async () => {
		const storage = new MemoryStorage();
		const result = await submitRegistrationAttempt({
			storage,
			actorId: null,
			accessToken: null,
			payload,
			turnstileToken: 'challenge',
			credentialFactory: () => credential,
			submit: async () => {
				throw new ApiRequestError(400, 'Invalid roster');
			}
		});
		expect(result).toMatchObject({ status: 'editable' });
		expect(listAccess(storage, 9)).toEqual([]);
	});

	it.each([
		[409, 'resolution-required'],
		[401, 'account-session-required'],
		[429, 'retryable']
	] as const)(
		'preserves uncertain access when replay receives HTTP %i',
		async (status, expected) => {
			const storage = new MemoryStorage();
			const entry = unresolved();
			const result = await recoverRegistrationAttempt({
				storage,
				entry,
				currentActorId: 7,
				accessToken: 'account-token',
				turnstileToken: 'fresh',
				resume: async () => {
					throw new ApiRequestError(404, 'Not found');
				},
				submit: async () => {
					throw new ApiRequestError(status, 'Rejected');
				}
			});
			expect(result).toMatchObject({ status: expected, credential });
			expect(listAccess(storage, 9)).toEqual([entry]);
		}
	);

	it('makes quota failure observable and does not submit without retaining the key', async () => {
		const storage = new MemoryStorage();
		storage.setItem = () => {
			throw new DOMException('quota', 'QuotaExceededError');
		};
		const submit = vi.fn();
		const result = await submitRegistrationAttempt({
			storage,
			actorId: null,
			accessToken: null,
			payload,
			turnstileToken: 'challenge',
			credentialFactory: () => credential,
			submit
		});
		expect(result).toMatchObject({ status: 'storage-unavailable', credential });
		expect(submit).not.toHaveBeenCalled();
	});
});
