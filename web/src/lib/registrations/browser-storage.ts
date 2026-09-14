import type { RegistrationSubmissionPayload } from '$lib/api/types';

const DRAFT_PREFIX = 'usec-registration-draft:v1:';
const ACCESS_PREFIX = 'usec-registration-access:v1:';
const DRAFT_LIFETIME_MS = 7 * 24 * 60 * 60 * 1000;
const CREDENTIAL_PATTERN = /^[0-9a-f]{64}$/;

export type DraftStage = 'details' | 'roster' | 'review';

export interface RegistrationDraft {
	version: 1;
	gameId: number;
	updatedAt: number;
	stage: DraftStage;
	fields: RegistrationSubmissionPayload;
	institutionLabels: Record<string, string>;
}

type SavedRegistrationAccessBase = {
	version: 1;
	gameId: number;
	credential: string;
};

export type PendingSavedRegistrationAccess = SavedRegistrationAccessBase & {
	attemptState: 'prepared' | 'uncertain';
	registrationId: null;
	actorId: number | null;
	submittedPayload: RegistrationSubmissionPayload;
};

export type SubmittedSavedRegistrationAccess = SavedRegistrationAccessBase & {
	attemptState: 'submitted';
	registrationId: number;
};

export type SavedRegistrationAccess =
	PendingSavedRegistrationAccess | SubmittedSavedRegistrationAccess;

type RecordValue = Record<string, unknown>;

function isRecord(value: unknown): value is RecordValue {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: RecordValue, required: string[], optional: string[] = []): boolean {
	const keys = Object.keys(value);
	return (
		required.every((key) => key in value) &&
		keys.every((key) => required.includes(key) || optional.includes(key))
	);
}

function isPositiveInteger(value: unknown): value is number {
	return Number.isInteger(value) && Number(value) > 0;
}

function isNonNegativeInteger(value: unknown): value is number {
	return Number.isInteger(value) && Number(value) >= 0;
}

function isInstitutionChoice(value: RecordValue, allowBlankLabel = false): boolean {
	const hasId = 'institution_id' in value;
	const hasLabel = 'institution_label' in value;
	return (
		hasId !== hasLabel &&
		(!hasId || isPositiveInteger(value.institution_id)) &&
		(!hasLabel ||
			(typeof value.institution_label === 'string' &&
				(allowBlankLabel || value.institution_label.trim() !== '')))
	);
}

function isMember(value: unknown, allowBlankInstitution = false): boolean {
	if (!isRecord(value)) return false;
	if (
		!hasOnlyKeys(
			value,
			[
				'first_name_snapshot',
				'last_name_snapshot',
				'date_of_birth_snapshot',
				'student_id_snapshot',
				'gamer_tag_snapshot',
				'is_captain',
				'roster_role',
				'display_order'
			],
			['institution_id', 'institution_label']
		)
	)
		return false;
	return (
		[
			'first_name_snapshot',
			'last_name_snapshot',
			'date_of_birth_snapshot',
			'student_id_snapshot',
			'gamer_tag_snapshot'
		].every((key) => typeof value[key] === 'string') &&
		typeof value.is_captain === 'boolean' &&
		(value.roster_role === 'main' || value.roster_role === 'substitute') &&
		isNonNegativeInteger(value.display_order) &&
		isInstitutionChoice(value, allowBlankInstitution)
	);
}

function isSubmissionPayload(
	value: unknown,
	allowBlankInstitution = false
): value is RegistrationSubmissionPayload {
	if (!isRecord(value)) return false;
	if (
		!hasOnlyKeys(
			value,
			[
				'tournament_game',
				'team_name',
				'team_tag',
				'submitter_role',
				'contact_facebook_snapshot',
				'contact_phone_snapshot',
				'members'
			],
			['contact_email_snapshot', 'contact_discord_snapshot', 'manager_name_snapshot']
		)
	)
		return false;
	return (
		isPositiveInteger(value.tournament_game) &&
		['team_name', 'team_tag', 'contact_facebook_snapshot', 'contact_phone_snapshot'].every(
			(key) => typeof value[key] === 'string'
		) &&
		['contact_email_snapshot', 'contact_discord_snapshot', 'manager_name_snapshot'].every(
			(key) => !(key in value) || typeof value[key] === 'string'
		) &&
		(value.submitter_role === 'captain' || value.submitter_role === 'manager') &&
		Array.isArray(value.members) &&
		value.members.every((member) => isMember(member, allowBlankInstitution))
	);
}

function isLabels(value: unknown): value is Record<string, string> {
	return isRecord(value) && Object.values(value).every((label) => typeof label === 'string');
}

function parseDraft(value: unknown, gameId: number): RegistrationDraft | null {
	if (
		!isRecord(value) ||
		!hasOnlyKeys(value, ['version', 'gameId', 'updatedAt', 'stage', 'fields', 'institutionLabels'])
	)
		return null;
	if (value.version !== 1 || value.gameId !== gameId || !isPositiveInteger(value.gameId))
		return null;
	if (
		typeof value.updatedAt !== 'number' ||
		!Number.isFinite(value.updatedAt) ||
		value.updatedAt < 0
	)
		return null;
	if (value.stage !== 'details' && value.stage !== 'roster' && value.stage !== 'review')
		return null;
	if (
		!isSubmissionPayload(value.fields, true) ||
		value.fields.tournament_game !== gameId ||
		!isLabels(value.institutionLabels)
	)
		return null;
	return value as unknown as RegistrationDraft;
}

function parseAccess(value: unknown, storageCredential: string): SavedRegistrationAccess | null {
	if (
		!isRecord(value) ||
		value.version !== 1 ||
		!isPositiveInteger(value.gameId) ||
		value.credential !== storageCredential ||
		!CREDENTIAL_PATTERN.test(storageCredential)
	)
		return null;
	if (value.attemptState === 'submitted') {
		if (
			!hasOnlyKeys(value, ['version', 'gameId', 'credential', 'attemptState', 'registrationId']) ||
			!isPositiveInteger(value.registrationId)
		)
			return null;
		return value as unknown as SavedRegistrationAccess;
	}
	if (value.attemptState !== 'prepared' && value.attemptState !== 'uncertain') return null;
	if (
		!hasOnlyKeys(value, [
			'version',
			'gameId',
			'credential',
			'attemptState',
			'registrationId',
			'actorId',
			'submittedPayload'
		])
	)
		return null;
	if (
		value.registrationId !== null ||
		(value.actorId !== null && !isPositiveInteger(value.actorId))
	)
		return null;
	if (
		!isSubmissionPayload(value.submittedPayload) ||
		value.submittedPayload.tournament_game !== value.gameId
	)
		return null;
	return value as unknown as SavedRegistrationAccess;
}

function parseJson(raw: string | null): unknown {
	if (raw === null) return null;
	try {
		return JSON.parse(raw);
	} catch {
		return null;
	}
}

export function readDraft(storage: Storage, gameId: number, now: number): RegistrationDraft | null {
	let raw: string | null;
	try {
		raw = storage.getItem(`${DRAFT_PREFIX}${gameId}`);
	} catch {
		return null;
	}
	const draft = parseDraft(parseJson(raw), gameId);
	if (!draft || now - draft.updatedAt >= DRAFT_LIFETIME_MS) return null;
	return draft;
}

export function writeDraft(storage: Storage, draft: RegistrationDraft): boolean {
	const safe = parseDraft(draft, draft.gameId);
	if (!safe) return false;
	try {
		storage.setItem(`${DRAFT_PREFIX}${safe.gameId}`, JSON.stringify(safe));
		return true;
	} catch {
		return false;
	}
}

export function clearDraft(storage: Storage, gameId: number): boolean {
	try {
		storage.removeItem(`${DRAFT_PREFIX}${gameId}`);
		return true;
	} catch {
		return false;
	}
}

export function createCredential(): string {
	const bytes = crypto.getRandomValues(new Uint8Array(32));
	return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function saveAccess(storage: Storage, entry: SavedRegistrationAccess): boolean {
	const safe = parseAccess(entry, entry.credential);
	if (!safe) return false;
	try {
		storage.setItem(`${ACCESS_PREFIX}${safe.credential}`, JSON.stringify(safe));
		return true;
	} catch {
		return false;
	}
}

function readAccessEntries(storage: Storage): SavedRegistrationAccess[] {
	const entries: SavedRegistrationAccess[] = [];
	let length: number;
	try {
		length = storage.length;
	} catch {
		return entries;
	}
	for (let index = 0; index < length; index += 1) {
		let key: string | null;
		try {
			key = storage.key(index);
		} catch {
			continue;
		}
		if (!key?.startsWith(ACCESS_PREFIX)) continue;
		const credential = key.slice(ACCESS_PREFIX.length);
		let raw: string | null;
		try {
			raw = storage.getItem(key);
		} catch {
			continue;
		}
		const entry = parseAccess(parseJson(raw), credential);
		if (entry) entries.push(entry);
	}
	return entries;
}

export function listAccess(storage: Storage, gameId: number): SavedRegistrationAccess[] {
	return readAccessEntries(storage).filter((entry) => entry.gameId === gameId);
}

export function findSubmittedAccess(
	storage: Storage,
	registrationId: number
): SubmittedSavedRegistrationAccess | null {
	if (!isPositiveInteger(registrationId)) return null;
	return (
		readAccessEntries(storage).find(
			(entry): entry is SubmittedSavedRegistrationAccess =>
				entry.attemptState === 'submitted' && entry.registrationId === registrationId
		) ?? null
	);
}

export function forgetAccess(storage: Storage, credential: string): boolean {
	if (!CREDENTIAL_PATTERN.test(credential)) return false;
	try {
		storage.removeItem(`${ACCESS_PREFIX}${credential}`);
		return true;
	} catch {
		return false;
	}
}

class CurrentPageStorage implements Storage {
	private readonly memory = new Map<string, string>();
	private primary: Storage | null;
	private onFailure: () => void;

	constructor(primary: Storage | null, onFailure: () => void) {
		this.primary = primary;
		this.onFailure = onFailure;
	}

	private fail() {
		this.primary = null;
		this.onFailure();
	}

	private keys(): string[] {
		if (this.primary) {
			try {
				const primaryKeys: string[] = [];
				for (let index = 0; index < this.primary.length; index += 1) {
					const key = this.primary.key(index);
					if (key !== null) primaryKeys.push(key);
				}
				const authoritativeKeys = new Set(primaryKeys);
				for (const key of this.memory.keys()) {
					if (!authoritativeKeys.has(key)) this.memory.delete(key);
				}
				return primaryKeys;
			} catch {
				this.fail();
			}
		}
		return [...this.memory.keys()];
	}

	get length() {
		return this.keys().length;
	}
	clear() {
		this.memory.clear();
		if (this.primary)
			try {
				this.primary.clear();
			} catch {
				this.fail();
			}
	}
	getItem(key: string) {
		if (this.primary)
			try {
				const value = this.primary.getItem(key);
				if (value === null) this.memory.delete(key);
				else this.memory.set(key, value);
				return value;
			} catch {
				this.fail();
			}
		return this.memory.get(key) ?? null;
	}
	key(index: number) {
		return this.keys()[index] ?? null;
	}
	removeItem(key: string) {
		this.memory.delete(key);
		if (this.primary)
			try {
				this.primary.removeItem(key);
			} catch {
				this.fail();
			}
	}
	setItem(key: string, value: string) {
		this.memory.set(key, value);
		if (this.primary)
			try {
				this.primary.setItem(key, value);
			} catch {
				this.fail();
			}
	}
}

export interface RegistrationStorageAccess {
	storage: Storage;
	readonly persistenceWarning: string | null;
}

export function createRegistrationStorage(
	acquire: () => Storage = () => localStorage
): RegistrationStorageAccess {
	let warning: string | null = null;
	let primary: Storage | null = null;
	try {
		primary = acquire();
	} catch {
		warning =
			'Progress can only be retained on this current page because browser storage is unavailable.';
	}
	const storage = new CurrentPageStorage(primary, () => {
		warning =
			'Progress can only be retained on this current page because browser storage is unavailable.';
	});
	return {
		storage,
		get persistenceWarning() {
			return warning;
		}
	};
}

let browserStorageAccess: RegistrationStorageAccess | null = null;

/** Shared by registration and payment routes in one browser page lifetime. */
export function getRegistrationStorage(): RegistrationStorageAccess {
	if (typeof window === 'undefined')
		return createRegistrationStorage(() => {
			throw new Error('SSR');
		});
	if (!browserStorageAccess)
		browserStorageAccess = createRegistrationStorage(() => window.localStorage);
	return browserStorageAccess;
}
