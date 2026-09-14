import { describe, expect, it } from 'vitest';
import {
	clearDraft,
	createCredential,
	createRegistrationStorage,
	findSubmittedAccess,
	forgetAccess,
	listAccess,
	readDraft,
	saveAccess,
	writeDraft,
	type RegistrationDraft,
	type SavedRegistrationAccess
} from './browser-storage';

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

const credentialA = '1'.repeat(64);
const credentialB = '2'.repeat(64);
const payload = {
	tournament_game: 9,
	team_name: 'Saigon Sentinels',
	team_tag: 'SGS',
	submitter_role: 'captain' as const,
	contact_facebook_snapshot: 'facebook.com/captain',
	contact_phone_snapshot: '0909000111',
	contact_email_snapshot: 'captain@example.test',
	contact_discord_snapshot: 'captain_handle',
	members: [
		{
			first_name_snapshot: 'An',
			last_name_snapshot: 'Nguyen',
			date_of_birth_snapshot: '2005-04-03',
			student_id_snapshot: 'SV123',
			gamer_tag_snapshot: 'Player One',
			institution_id: 12,
			is_captain: true,
			roster_role: 'main' as const,
			display_order: 0
		}
	]
};
const draft: RegistrationDraft = {
	version: 1,
	gameId: 9,
	updatedAt: 1000,
	stage: 'roster',
	fields: payload,
	institutionLabels: { '0': 'University of Science' }
};

describe('registration browser storage', () => {
	it('round-trips allowlisted registration fields and expires only the draft after seven days', () => {
		const storage = new MemoryStorage();
		const access: SavedRegistrationAccess = {
			version: 1,
			gameId: 9,
			credential: credentialA,
			attemptState: 'prepared',
			registrationId: null,
			actorId: null,
			submittedPayload: payload
		};

		expect(writeDraft(storage, draft)).toBe(true);
		expect(saveAccess(storage, access)).toBe(true);
		expect(readDraft(storage, 9, 1000)).toEqual(draft);
		expect(readDraft(storage, 9, 1000 + 7 * 24 * 60 * 60 * 1000)).toBeNull();
		expect(listAccess(storage, 9)).toEqual([access]);
	});

	it('round-trips an incomplete roster draft while rejecting it as a pending submission', () => {
		const storage = new MemoryStorage();
		const memberWithoutInstitution = {
			first_name_snapshot: 'An',
			last_name_snapshot: 'Nguyen',
			date_of_birth_snapshot: '2005-04-03',
			student_id_snapshot: 'SV123',
			gamer_tag_snapshot: 'Player One',
			is_captain: true,
			roster_role: 'main' as const,
			display_order: 0
		};
		const incompleteDraft: RegistrationDraft = {
			...draft,
			fields: {
				...payload,
				members: [{ ...memberWithoutInstitution, institution_label: '' }]
			},
			institutionLabels: {}
		};

		expect(writeDraft(storage, incompleteDraft)).toBe(true);
		expect(readDraft(storage, 9, 1000)).toEqual(incompleteDraft);
		expect(
			saveAccess(storage, {
				version: 1,
				gameId: 9,
				credential: credentialA,
				attemptState: 'prepared',
				registrationId: null,
				actorId: null,
				submittedPayload: incompleteDraft.fields
			})
		).toBe(false);
	});

	it('rejects malformed, wrong-division, stale-version, invalid-stage, and invalid-payload drafts', () => {
		const storage = new MemoryStorage();
		const key = 'usec-registration-draft:v1:9';
		for (const value of [
			'{',
			{ ...draft, version: 2 },
			{ ...draft, gameId: 10 },
			{ ...draft, stage: 'payment' },
			{ ...draft, fields: { ...payload, members: 'invalid' } },
			{ ...draft, fields: { ...payload, turnstile_token: 'secret' } },
			{ ...draft, fields: { ...payload, accessToken: 'jwt' } },
			{ ...draft, fields: { ...payload, proof_file: 'image bytes' } }
		]) {
			storage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
			expect(readDraft(storage, 9, 1000)).toBeNull();
		}
	});

	it('enumerates separate access entries and forgets only the selected credential', () => {
		const storage = new MemoryStorage();
		const first: SavedRegistrationAccess = {
			version: 1,
			gameId: 9,
			credential: credentialA,
			attemptState: 'submitted',
			registrationId: 41
		};
		const second: SavedRegistrationAccess = {
			version: 1,
			gameId: 9,
			credential: credentialB,
			attemptState: 'submitted',
			registrationId: 42
		};
		expect(saveAccess(storage, first)).toBe(true);
		expect(saveAccess(storage, second)).toBe(true);
		expect(writeDraft(storage, draft)).toBe(true);

		expect(listAccess(storage, 9)).toEqual([first, second]);
		expect(clearDraft(storage, 9)).toBe(true);
		expect(listAccess(storage, 9)).toEqual([first, second]);
		expect(forgetAccess(storage, credentialA)).toBe(true);
		expect(listAccess(storage, 9)).toEqual([second]);
	});

	it('finds submitted access by registration ID without requiring division URL state', () => {
		const storage = new MemoryStorage();
		const expected: SavedRegistrationAccess = {
			version: 1,
			gameId: 14,
			credential: credentialB,
			attemptState: 'submitted',
			registrationId: 84
		};
		expect(
			saveAccess(storage, {
				version: 1,
				gameId: 9,
				credential: credentialA,
				attemptState: 'submitted',
				registrationId: 41
			})
		).toBe(true);
		expect(saveAccess(storage, expected)).toBe(true);
		storage.setItem(
			`usec-registration-access:v1:${'3'.repeat(64)}`,
			JSON.stringify({ ...expected, credential: '3'.repeat(64), registrationId: '84' })
		);

		expect(findSubmittedAccess(storage, 84)).toEqual(expected);
		expect(findSubmittedAccess(storage, 999)).toBeNull();
	});

	it('discards malformed access records and requires an explicit valid original actor', () => {
		const storage = new MemoryStorage();
		for (const [suffix, value] of [
			[
				'3'.repeat(64),
				{
					version: 1,
					gameId: 9,
					credential: '3'.repeat(64),
					attemptState: 'prepared',
					registrationId: null,
					submittedPayload: payload
				}
			],
			[
				'4'.repeat(64),
				{
					version: 1,
					gameId: 9,
					credential: '4'.repeat(64),
					attemptState: 'uncertain',
					registrationId: null,
					actorId: 0,
					submittedPayload: payload
				}
			],
			[
				'5'.repeat(64),
				{
					version: 1,
					gameId: 9,
					credential: '5'.repeat(64),
					attemptState: 'submitted',
					registrationId: null
				}
			],
			[
				'6'.repeat(64),
				{
					version: 1,
					gameId: 9,
					credential: '6'.repeat(64),
					attemptState: 'prepared',
					registrationId: null,
					actorId: null,
					submittedPayload: { ...payload, challenge: 'secret' }
				}
			]
		] as const) {
			storage.setItem(`usec-registration-access:v1:${suffix}`, JSON.stringify(value));
		}
		expect(listAccess(storage, 9)).toEqual([]);
	});

	it('returns failure instead of throwing when individual storage operations fail', () => {
		const failure = new DOMException('blocked', 'SecurityError');
		const storage = new MemoryStorage();
		storage.getItem = () => {
			throw failure;
		};
		storage.setItem = () => {
			throw failure;
		};
		storage.removeItem = () => {
			throw failure;
		};
		Object.defineProperty(storage, 'length', {
			get: () => {
				throw failure;
			}
		});

		expect(readDraft(storage, 9, 1000)).toBeNull();
		expect(writeDraft(storage, draft)).toBe(false);
		expect(clearDraft(storage, 9)).toBe(false);
		expect(
			saveAccess(storage, {
				version: 1,
				gameId: 9,
				credential: credentialA,
				attemptState: 'submitted',
				registrationId: 41
			})
		).toBe(false);
		expect(listAccess(storage, 9)).toEqual([]);
		expect(forgetAccess(storage, credentialA)).toBe(false);
	});

	it('falls back to current-page memory and exposes a persistence warning', () => {
		const access = createRegistrationStorage(() => {
			throw new DOMException('blocked', 'SecurityError');
		});
		expect(writeDraft(access.storage, draft)).toBe(true);
		expect(readDraft(access.storage, 9, 1000)).toEqual(draft);
		expect(access.persistenceWarning).toMatch(/current page/i);
	});

	it('keeps current-page writes when acquired storage later rejects an operation', () => {
		const primary = new MemoryStorage();
		primary.setItem = () => {
			throw new DOMException('quota', 'QuotaExceededError');
		};
		const access = createRegistrationStorage(() => primary);
		expect(writeDraft(access.storage, draft)).toBe(true);
		expect(readDraft(access.storage, 9, 1000)).toEqual(draft);
		expect(access.persistenceWarning).toMatch(/current page/i);
	});

	it('retains access observed from primary storage when a later write forces memory fallback', () => {
		const primary = new MemoryStorage();
		const submitted: SavedRegistrationAccess = {
			version: 1,
			gameId: 9,
			credential: credentialA,
			attemptState: 'submitted',
			registrationId: 41
		};
		expect(saveAccess(primary, submitted)).toBe(true);
		const access = createRegistrationStorage(() => primary);
		expect(listAccess(access.storage, 9)).toEqual([submitted]);

		primary.setItem = () => {
			throw new DOMException('quota', 'QuotaExceededError');
		};
		expect(writeDraft(access.storage, draft)).toBe(true);
		expect(access.persistenceWarning).toMatch(/current page/i);
		expect(listAccess(access.storage, 9)).toEqual([submitted]);
	});

	it('uses healthy primary storage as authority after another tab overwrites or removes an entry', () => {
		const primary = new MemoryStorage();
		const original: SavedRegistrationAccess = {
			version: 1,
			gameId: 9,
			credential: credentialA,
			attemptState: 'submitted',
			registrationId: 41
		};
		const replaced: SavedRegistrationAccess = { ...original, registrationId: 84 };
		expect(saveAccess(primary, original)).toBe(true);
		const access = createRegistrationStorage(() => primary);
		expect(listAccess(access.storage, 9)).toEqual([original]);

		expect(saveAccess(primary, replaced)).toBe(true);
		expect(listAccess(access.storage, 9)).toEqual([replaced]);
		expect(forgetAccess(primary, credentialA)).toBe(true);
		expect(listAccess(access.storage, 9)).toEqual([]);
	});

	it('uses 32 cryptographically random bytes encoded as lowercase hex', () => {
		const credential = createCredential();
		expect(credential).toMatch(/^[0-9a-f]{64}$/);
		expect(createCredential()).not.toBe(credential);
	});
});
