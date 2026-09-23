import { beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { ApiRequestError } from '$lib/api/client';
import {
	getRegistration,
	listRegistrations,
	submitPaymentAttempt,
	submitRegistration,
	submitSavedRegistration,
	getPaymentSession,
	uploadPaymentProof
} from '$lib/api/registrations';
import type { PublicTournament, PublicTournamentGame, RegistrationRead } from '$lib/api/types';
import { clearSession, getAccessToken } from '$lib/auth/session';
import { replaceInternalLocation } from '$lib/auth/navigation';
import { overwriteGetLocale } from '$lib/paraglide/runtime';

import { registrationRoutePage as mockPage } from '$lib/test/registration-route-state.svelte';
const turnstileTokens = vi.hoisted(() => ({
	'registration-submit': 'registration-submit-token',
	'payment-proof-submit': 'payment-proof-submit-token'
}));
const turnstileDependencies = vi.hoisted(() => ({ reset: vi.fn() }));

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_TURNSTILE_SITE_KEY: 'site-key' } }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));
vi.mock('$lib/states/auth-state.svelte', () => ({
	authState: { initialize: vi.fn().mockResolvedValue(null), currentUser: null }
}));
vi.mock('$app/state', async () => ({
	page: (await import('$lib/test/registration-route-state.svelte')).registrationRoutePage
}));
vi.mock('$lib/api/registrations', () => ({
	reservePaymentInstructions: vi.fn().mockResolvedValue({
		token: 'payment-token',
		transfer_content_template: '{participant} thanh toan le phi Summer',
		transfer_content_limit: 100,
		amount: '50000.00',
		currency: 'VND'
	}),
	getPaymentInstructions: vi.fn().mockResolvedValue({
		transfer_content: 'PLAYER thanh toan le phi Summer',
		transfer_content_limit: 100
	}),
	getRegistration: vi.fn(),
	listRegistrations: vi.fn(),
	submitPaymentAttempt: vi.fn(),
	submitRegistration: vi.fn(),
	submitSavedRegistration: vi.fn(),
	resumeRegistration: vi.fn(),
	getPaymentSession: vi.fn(),
	uploadPaymentProof: vi.fn()
}));
vi.mock('$lib/auth/session', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/auth/session')>()),
	getAccessToken: vi.fn(),
	clearSession: vi.fn()
}));
vi.mock('$lib/api/institutions', () => ({ searchInstitutions: vi.fn().mockResolvedValue([]) }));
vi.mock('$lib/auth/navigation', () => ({ replaceInternalLocation: vi.fn() }));

const game: PublicTournamentGame = {
	id: 10,
	game_name: 'Valorant',
	game_slug: 'valorant',
	main_roster_size: 2,
	substitute_limit: 0,
	registration_opens_at: '2026-07-01T00:00:00Z',
	registration_closes_at: '2026-07-31T00:00:00Z',
	registration_capacity: 16,
	capacity_remaining: 16,
	fee_amount: '50000.00',
	fee_currency: 'VND',
	registration_state: 'open',
	is_registration_open: true,
	payment_hold_minutes: 60,
	payment_available: true
};
const tournament: PublicTournament = {
	id: 1,
	name: 'USEC Summer 2026',
	slug: 'usec-summer-2026',
	description: '',
	cover_image: null,
	starts_at: null,
	ends_at: null,
	location: 'HCMUS',
	is_featured: false,
	students_only: false,
	tournament_games: [game]
};
const registration: RegistrationRead = {
	id: 33,
	tournament_game: {
		id: game.id,
		tournament_name: tournament.name,
		game_name: game.game_name,
		main_roster_size: game.main_roster_size,
		substitute_limit: game.substitute_limit,
		fee_amount: game.fee_amount,
		fee_currency: game.fee_currency
	},
	team_name: 'Blue Team',
	team_tag: 'BLUE',
	status: 'SUBMITTED',
	fee_amount_snapshot: '50000.00',
	fee_currency_snapshot: 'VND',
	submitted_at: '2026-07-19T00:00:00Z',
	payment_required: true,
	payment_reference: 'USEC23456789AB',
	payment_state: 'UNPAID',
	payment_due_at: '2026-07-19T01:00:00Z',
	expired: false,
	members: [
		{
			gamer_tag_snapshot: 'captain',
			school_snapshot: 'HCMUS',
			roster_role: 'main',
			is_captain: true,
			display_order: 1
		},
		{
			gamer_tag_snapshot: 'teammate',
			school_snapshot: 'HCMUS',
			roster_role: 'main',
			is_captain: false,
			display_order: 2
		}
	],
	status_events: [{ to_status: 'SUBMITTED', created_at: '2026-07-19T00:00:00Z' }],
	payment_attempts: []
};

beforeEach(() => {
	sessionStorage.clear();
	localStorage.clear();
	vi.mocked(submitSavedRegistration).mockReset().mockResolvedValue(registration);
	vi.mocked(getAccessToken).mockReturnValue(null);
	overwriteGetLocale(() => 'en');
	mockPage.url = new URL('https://usec.test/tournaments/usec-summer-2026/games/10/register');
	mockPage.params = { id: '33' };
	vi.mocked(goto).mockReset().mockResolvedValue(undefined);
	vi.mocked(getAccessToken).mockReset().mockReturnValue(null);
	vi.mocked(listRegistrations).mockReset().mockResolvedValue([registration]);
	vi.mocked(getRegistration).mockReset().mockResolvedValue(registration);
	vi.mocked(submitRegistration).mockReset().mockResolvedValue(registration);
	vi.mocked(submitPaymentAttempt).mockReset().mockResolvedValue({
		id: 4,
		status: 'PENDING',
		amount: '50000.00',
		currency: 'VND',
		created_at: '2026-07-19T01:00:00Z'
	});
	vi.mocked(replaceInternalLocation).mockReset();
	vi.mocked(clearSession).mockReset();
	turnstileDependencies.reset.mockReset();
	turnstileTokens['registration-submit'] = 'registration-submit-token';
	turnstileTokens['payment-proof-submit'] = 'payment-proof-submit-token';
	document.head.querySelectorAll('script[data-turnstile-api]').forEach((script) => script.remove());
	const turnstileScript = document.createElement('script');
	turnstileScript.dataset.turnstileApi = 'true';
	document.head.appendChild(turnstileScript);
	window.turnstile = {
		render: (_container, options) => {
			options.callback(turnstileTokens[options.action as keyof typeof turnstileTokens] ?? '');
			return 'widget-id';
		},
		reset: turnstileDependencies.reset
	};
});

import PaymentPanel from '$lib/components/registrations/RegistrationPaymentPanel.svelte';
import type { RegistrationPaymentSession } from '$lib/api/types';
const privateSession: RegistrationPaymentSession = {
	tournament_slug: tournament.slug,
	registration,
	payment_state: 'UNPAID',
	payment_due_at: '2026-07-19T01:00:00Z',
	server_now: '2026-07-19T00:00:00Z',
	expired: false,
	can_upload_proof: true,
	can_retry_registration: false,
	replacement_note: '',
	saved_submission: {
		tournament_game: 10,
		team_name: 'Blue Team',
		team_tag: 'BLUE',
		submitter_role: 'captain',
		manager_name_snapshot: '',
		contact_facebook_snapshot: 'fb',
		contact_phone_snapshot: '090',
		contact_email_snapshot: '',
		contact_discord_snapshot: '',
		members: []
	},
	institution_labels: {},
	instructions: {
		bank_name: 'Test Bank',
		bank_bin: '970422',
		account_number: '001234',
		account_holder: 'TEST HOLDER',
		amount: '50000',
		currency: 'VND',
		transfer_content: 'BLUE full original transfer content longer than twenty five',
		transfer_content_limit: 100,
		qr_payload: 'payload',
		qr_png_data_url: 'data:image/png;base64,iVBORw0KGgo=',
		qr_contains_transfer_content: false
	}
};
describe('private payment panel', () => {
	it('shows saved bank data and requires full text when the QR omits it', async () => {
		render(PaymentPanel, {
			session: privateSession,
			authority: { credential: 'ab'.repeat(32) },
			onupdated: vi.fn()
		});
		await expect.element(page.getByRole('heading', { name: 'Payment instructions' })).toBeVisible();
		await expect.element(page.getByRole('heading', { name: 'Payment proof' })).toBeVisible();
		await expect
			.element(page.getByRole('heading', { name: 'Registration status timeline' }))
			.toBeVisible();
		await expect.element(page.getByText('001234', { exact: true })).toBeVisible();
		await expect
			.element(
				page.getByText(
					'This QR contains only the bank and amount. Paste the full transfer content below into your banking app.'
				)
			)
			.toBeVisible();
		await expect.element(page.getByRole('img', { name: 'VietQR payment code' })).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Upload payment proof', exact: true }))
			.toBeVisible();
	});
	it.each(['PENDING', 'VERIFIED'] as const)(
		'protects %s reservations and hides actionable payment controls',
		async (state) => {
			render(PaymentPanel, {
				session: {
					...privateSession,
					payment_state: state,
					can_upload_proof: false,
					instructions: null
				},
				authority: { credential: 'ab'.repeat(32) },
				onupdated: vi.fn()
			});
			await expect.element(page.getByRole('button', { name: 'Refresh status' })).toBeVisible();
			await expect
				.element(page.getByRole('img', { name: 'VietQR payment code' }))
				.not.toBeInTheDocument();
			await expect
				.element(page.getByRole('button', { name: 'Upload payment proof', exact: true }))
				.not.toBeInTheDocument();
		}
	);
});

import PaymentPage from './registrations/[id]/payment/+page.svelte';
it('loads the private payment page with saved access and never falls through a wrong credential to account authority', async () => {
	localStorage.setItem(
		`usec-registration-access:v1:${'ab'.repeat(32)}`,
		JSON.stringify({
			version: 1,
			gameId: 10,
			credential: 'ab'.repeat(32),
			registrationId: 33,
			attemptState: 'submitted'
		})
	);
	vi.mocked(getAccessToken).mockReturnValue('owner-token');
	vi.mocked(getPaymentSession).mockRejectedValue(new ApiRequestError(404, 'Not found'));
	render(PaymentPage);
	await expect.element(page.getByText(/No saved access is available/)).toBeVisible();
	expect(getPaymentSession).toHaveBeenCalledWith(33, { credential: 'ab'.repeat(32) });
	await expect.element(page.getByText('001234')).not.toBeInTheDocument();
});
it('uploads validated proof with a fresh challenge and displays the returned protected status', async () => {
	vi.mocked(uploadPaymentProof).mockResolvedValue({
		...privateSession,
		payment_state: 'PENDING',
		can_upload_proof: false,
		instructions: null
	});
	const updated = vi.fn();
	render(PaymentPanel, {
		session: privateSession,
		authority: { credential: 'ab'.repeat(32) },
		onupdated: updated
	});
	await expect
		.element(page.getByRole('button', { name: 'Upload payment proof', exact: true }))
		.toBeVisible();
	const input = document.querySelector<HTMLInputElement>('input[type=file]')!;
	const transfer = new DataTransfer();
	transfer.items.add(new File(['proof'], 'proof.png', { type: 'image/png' }));
	input.files = transfer.files;
	input.dispatchEvent(new Event('change', { bubbles: true }));
	await page.getByRole('button', { name: 'Upload payment proof', exact: true }).click();
	await vi.waitFor(() => expect(updated).toHaveBeenCalled());
	const form = vi.mocked(uploadPaymentProof).mock.calls[0][1];
	expect(form.get('turnstile_token')).toBe('payment-proof-submit-token');
	expect(form.get('proof_file')).toBeInstanceOf(File);
	expect(turnstileDependencies.reset).toHaveBeenCalled();
});
it('shows copy failure without losing the full saved transfer content', async () => {
	const write = vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Denied'));
	render(PaymentPanel, {
		session: privateSession,
		authority: { credential: 'ab'.repeat(32) },
		onupdated: vi.fn()
	});
	await page.getByRole('button', { name: 'Copy Transfer content', exact: true }).click();
	await expect
		.element(page.getByText('Copy failed. Select and copy the displayed text manually.'))
		.toBeVisible();
	await expect
		.element(page.getByText(privateSession.instructions!.transfer_content, { exact: true }))
		.toBeVisible();
	write.mockRestore();
});
it('uses server time, refreshes at the deadline, and cleans visibility listeners on unmount', async () => {
	vi.mocked(getPaymentSession)
		.mockClear()
		.mockResolvedValue({
			...privateSession,
			expired: true,
			can_upload_proof: false,
			instructions: null
		});
	const updated = vi.fn();
	const view = render(PaymentPanel, {
		session: { ...privateSession, payment_due_at: '2026-07-19T00:00:01Z' },
		authority: { credential: 'ab'.repeat(32) },
		onupdated: updated
	});
	await vi.waitFor(() => expect(updated).toHaveBeenCalled(), { timeout: 2500 });
	await view.unmount();
	const calls = vi.mocked(getPaymentSession).mock.calls.length;
	document.dispatchEvent(new Event('visibilitychange'));
	await new Promise((resolve) => setTimeout(resolve, 50));
	expect(getPaymentSession).toHaveBeenCalledTimes(calls);
});
it('formats the countdown in hours and minutes without second-by-second churn', async () => {
	render(PaymentPanel, {
		session: { ...privateSession, payment_due_at: '2026-07-19T01:02:00Z' },
		authority: { credential: 'ab'.repeat(32) },
		onupdated: vi.fn()
	});
	await expect.element(page.getByText('Time remaining: 1 hr 2 min')).toBeVisible();
	await new Promise((resolve) => setTimeout(resolve, 1150));
	await expect.element(page.getByText('Time remaining: 1 hr 2 min')).toBeVisible();
});
it('shows a calm final-minute countdown instead of raw seconds', async () => {
	render(PaymentPanel, {
		session: { ...privateSession, payment_due_at: '2026-07-19T00:00:30Z' },
		authority: { credential: 'ab'.repeat(32) },
		onupdated: vi.fn()
	});
	await expect.element(page.getByText('Time remaining: less than 1 min')).toBeVisible();
});
import { getTournament } from '$lib/api/tournaments';
import { searchInstitutions } from '$lib/api/institutions';
vi.mock('$lib/api/tournaments', () => ({ getTournament: vi.fn() }));
it('expired payment has no actionable QR and copies still-valid schools into a fresh draft without changing history', async () => {
	vi.mocked(getTournament).mockResolvedValue(tournament);
	vi.mocked(searchInstitutions).mockResolvedValue([
		{
			id: 12,
			value: '12',
			label: 'Current school',
			code: '',
			shortName: '',
			eng: '',
			type: '',
			location: ''
		}
	]);
	const member = {
		first_name_snapshot: 'Player',
		last_name_snapshot: 'Example',
		gamer_tag_snapshot: 'captain',
		date_of_birth_snapshot: '2005-01-01',
		student_id_snapshot: '',
		institution_id: 12,
		roster_role: 'main' as const,
		is_captain: true,
		display_order: 1
	};
	const expired = {
		...privateSession,
		expired: true,
		can_upload_proof: false,
		can_retry_registration: true,
		instructions: null,
		institution_labels: { '1': 'Current school' },
		saved_submission: { ...privateSession.saved_submission, members: [member] }
	};
	render(PaymentPanel, {
		session: expired,
		authority: { credential: 'ab'.repeat(32) },
		onupdated: vi.fn()
	});
	await expect
		.element(page.getByRole('img', { name: 'VietQR payment code' }))
		.not.toBeInTheDocument();
	await page.getByRole('button', { name: 'Create a new editable draft' }).click();
	await vi.waitFor(() =>
		expect(goto).toHaveBeenCalledWith('/en/tournaments/usec-summer-2026/games/10/register')
	);
	const draft = JSON.parse(localStorage.getItem('usec-registration-draft:v1:10')!);
	expect(draft.fields.members[0].institution_id).toBe(12);
	expect(draft.institutionLabels['1']).toBe('Current school');
	expect(expired.saved_submission.members[0].institution_id).toBe(12);
});

function savedPayment(id: number, key: string) {
	localStorage.setItem(
		`usec-registration-access:v1:${key.repeat(32)}`,
		JSON.stringify({
			version: 1,
			gameId: 10,
			credential: key.repeat(32),
			registrationId: id,
			attemptState: 'submitted'
		})
	);
}
it('isolates private sessions while the same page navigates between saved registration IDs', async () => {
	savedPayment(33, 'ab');
	savedPayment(34, 'cd');
	vi.mocked(getPaymentSession)
		.mockReset()
		.mockImplementation(async (id) => ({
			...privateSession,
			registration: { ...registration, id, team_name: `Team ${id}` }
		}));
	render(PaymentPage);
	await expect.element(page.getByText(/Team 33/)).toBeVisible();
	mockPage.params = { id: '34' };
	mockPage.url = new URL('https://usec.test/registrations/34/payment');
	await expect.element(page.getByText(/Team 34/)).toBeVisible();
	await expect.element(page.getByText(/Team 33/)).not.toBeInTheDocument();
	await page.getByRole('button', { name: 'Refresh status' }).click();
	expect(vi.mocked(getPaymentSession).mock.lastCall).toEqual([34, { credential: 'cd'.repeat(32) }]);
});
it('clears the first record when the second route ID has no authority and ignores a late first response', async () => {
	savedPayment(33, 'ab');
	let finish!: (session: RegistrationPaymentSession) => void;
	vi.mocked(getPaymentSession)
		.mockReset()
		.mockImplementation(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
	render(PaymentPage);
	await vi.waitFor(() => expect(getPaymentSession).toHaveBeenCalledOnce());
	mockPage.params = { id: '34' };
	mockPage.url = new URL('https://usec.test/registrations/34/payment');
	await expect.element(page.getByText(/No saved access is available/)).toBeVisible();
	finish(privateSession);
	await new Promise((resolve) => setTimeout(resolve, 50));
	await expect.element(page.getByText('001234', { exact: true })).not.toBeInTheDocument();
	expect(getPaymentSession).toHaveBeenCalledOnce();
});
it('retains saved authority after a temporary load failure and offers retry', async () => {
	savedPayment(33, 'ab');
	vi.mocked(getPaymentSession)
		.mockReset()
		.mockRejectedValueOnce(new ApiRequestError(503, 'Unavailable'))
		.mockResolvedValueOnce(privateSession);
	render(PaymentPage);
	await expect
		.element(
			page.getByText(
				'Payment details could not be loaded. Your saved access is retained. Please try again.'
			)
		)
		.toBeVisible();
	await expect.element(page.getByText(/No saved access is available/)).not.toBeInTheDocument();
	await page.getByRole('button', { name: 'Try loading again' }).click();
	await expect.element(page.getByText('001234', { exact: true })).toBeVisible();
	expect(vi.mocked(getPaymentSession).mock.lastCall).toEqual([33, { credential: 'ab'.repeat(32) }]);
});
it('directs terminal participants who already transferred to the organizers', async () => {
	vi.mocked(getTournament).mockResolvedValue(tournament);
	render(PaymentPanel, {
		session: { ...privateSession, expired: true, instructions: null, can_upload_proof: false },
		authority: { credential: 'ab'.repeat(32) },
		onupdated: vi.fn()
	});
	await expect
		.element(
			page.getByText(
				'If you already transferred money, contact the organizers with your registration reference and transfer proof before trying again.'
			)
		)
		.toBeVisible();
	await expect
		.element(page.getByRole('link', { name: 'Contact organizers' }))
		.toHaveAttribute('href', 'https://facebook.com/hcmusec');
});
it('removes an already displayed private session when navigating to a registration without saved authority', async () => {
	savedPayment(33, 'ab');
	vi.mocked(getPaymentSession).mockReset().mockResolvedValue(privateSession);
	render(PaymentPage);
	await expect.element(page.getByText('001234', { exact: true })).toBeVisible();
	mockPage.params = { id: '34' };
	mockPage.url = new URL('https://usec.test/registrations/34/payment');
	await expect.element(page.getByText(/No saved access is available/)).toBeVisible();
	await expect.element(page.getByText('001234', { exact: true })).not.toBeInTheDocument();
	expect(getPaymentSession).toHaveBeenCalledOnce();
});
