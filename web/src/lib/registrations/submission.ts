import { ApiRequestError } from '$lib/api/client';
import { resumeRegistration, submitSavedRegistration } from '$lib/api/registrations';
import type {
	RegistrationPaymentSession,
	RegistrationRead,
	RegistrationSubmissionPayload
} from '$lib/api/types';
import {
	clearDraft,
	createCredential,
	forgetAccess,
	saveAccess,
	type PendingSavedRegistrationAccess,
	type SavedRegistrationAccess
} from './browser-storage';

type SubmitClient = typeof submitSavedRegistration;
type ResumeClient = typeof resumeRegistration;

export interface RegistrationSubmissionAttemptInput {
	storage: Storage;
	actorId: number | null;
	accessToken: string | null;
	payload: RegistrationSubmissionPayload;
	turnstileToken: string;
	credentialFactory?: () => string;
	submit?: SubmitClient;
}

export interface RegistrationRecoveryAttemptInput {
	storage: Storage;
	entry: PendingSavedRegistrationAccess;
	currentActorId: number | null;
	accessToken: string | null;
	turnstileToken: string | null;
	// A migrated browser may recover a committed entry before deciding to start unpaid.
	allowReplay?: boolean;
	resume?: ResumeClient;
	submit?: SubmitClient;
}

export type RegistrationSubmissionResult =
	| { status: 'submitted'; credential: string; registration: RegistrationRead; session?: never }
	| {
			status: 'submitted';
			credential: string;
			session: RegistrationPaymentSession;
			registration?: never;
	  }
	| {
			status:
				| 'editable'
				| 'uncertain'
				| 'retryable'
				| 'resolution-required'
				| 'account-session-required'
				| 'actor-required'
				| 'challenge-required'
				| 'storage-unavailable'
				| 'invalid-actor';
			credential: string;
			error?: unknown;
	  };

function submittedAccess(
	entry: Pick<SavedRegistrationAccess, 'gameId' | 'credential'>,
	registrationId: number
): SavedRegistrationAccess {
	return {
		version: 1,
		gameId: entry.gameId,
		credential: entry.credential,
		attemptState: 'submitted',
		registrationId
	};
}

function unresolvedAccess(
	entry: PendingSavedRegistrationAccess,
	attemptState: 'prepared' | 'uncertain'
): PendingSavedRegistrationAccess {
	return { ...entry, attemptState };
}

function finishSubmission(
	storage: Storage,
	entry: PendingSavedRegistrationAccess,
	registration: RegistrationRead
) {
	saveAccess(storage, submittedAccess(entry, registration.id));
	clearDraft(storage, entry.gameId);
}

function isHttpError(error: unknown, status: number): boolean {
	return error instanceof ApiRequestError && error.status === status;
}

export async function submitRegistrationAttempt(
	input: RegistrationSubmissionAttemptInput
): Promise<RegistrationSubmissionResult> {
	const credential = (input.credentialFactory ?? createCredential)();
	if (input.actorId !== null && (!Number.isInteger(input.actorId) || input.actorId <= 0)) {
		return { status: 'invalid-actor', credential };
	}
	if (input.actorId !== null && !input.accessToken) {
		return { status: 'account-session-required', credential };
	}
	if (input.actorId === null && input.accessToken) {
		return { status: 'actor-required', credential };
	}
	const entry: PendingSavedRegistrationAccess = {
		version: 1,
		gameId: input.payload.tournament_game,
		credential,
		attemptState: 'prepared',
		registrationId: null,
		actorId: input.actorId,
		submittedPayload: input.payload
	};
	if (!saveAccess(input.storage, entry)) return { status: 'storage-unavailable', credential };

	try {
		const registration = await (input.submit ?? submitSavedRegistration)(
			input.accessToken,
			entry.submittedPayload,
			input.turnstileToken,
			credential
		);
		finishSubmission(input.storage, entry, registration);
		return { status: 'submitted', credential, registration };
	} catch (error) {
		if (isHttpError(error, 400) || isHttpError(error, 422)) {
			forgetAccess(input.storage, credential);
			return { status: 'editable', credential, error };
		}
		if (isHttpError(error, 401)) return { status: 'account-session-required', credential, error };
		if (isHttpError(error, 429)) return { status: 'retryable', credential, error };
		if (error instanceof ApiRequestError) {
			saveAccess(input.storage, unresolvedAccess(entry, 'uncertain'));
			return { status: 'resolution-required', credential, error };
		}
		saveAccess(input.storage, unresolvedAccess(entry, 'uncertain'));
		return { status: 'uncertain', credential, error };
	}
}

export async function recoverRegistrationAttempt(
	input: RegistrationRecoveryAttemptInput
): Promise<RegistrationSubmissionResult> {
	const entry = unresolvedAccess(input.entry, 'uncertain');
	const credential = entry.credential;
	if (!saveAccess(input.storage, entry)) return { status: 'storage-unavailable', credential };

	try {
		const session = await (input.resume ?? resumeRegistration)(credential);
		saveAccess(input.storage, submittedAccess(entry, session.registration.id));
		clearDraft(input.storage, entry.gameId);
		return { status: 'submitted', credential, session };
	} catch (error) {
		if (!isHttpError(error, 404)) {
			return { status: 'resolution-required', credential, error };
		}
	}

	if (input.allowReplay === false) return { status: 'resolution-required', credential };

	if (entry.actorId !== input.currentActorId) {
		return {
			status:
				entry.actorId !== null && input.currentActorId === null
					? 'account-session-required'
					: 'actor-required',
			credential
		};
	}
	if (entry.actorId !== null && !input.accessToken) {
		return { status: 'account-session-required', credential };
	}
	if (!input.turnstileToken) return { status: 'challenge-required', credential };

	try {
		const registration = await (input.submit ?? submitSavedRegistration)(
			input.accessToken,
			entry.submittedPayload,
			input.turnstileToken,
			credential
		);
		finishSubmission(input.storage, entry, registration);
		return { status: 'submitted', credential, registration };
	} catch (error) {
		if (isHttpError(error, 401)) return { status: 'account-session-required', credential, error };
		if (isHttpError(error, 429)) return { status: 'retryable', credential, error };
		if (error instanceof ApiRequestError)
			return { status: 'resolution-required', credential, error };
		return { status: 'uncertain', credential, error };
	}
}
