import {
	createRegistrationStorage,
	getRegistrationStorage
} from '$lib/registrations/browser-storage';
vi.mock('$lib/registrations/browser-storage', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/registrations/browser-storage')>();
	return { ...actual, getRegistrationStorage: vi.fn() };
});
import * as m from '$lib/paraglide/messages';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { ApiRequestError } from '$lib/api/client';
import {
	getRegistration,
	listRegistrations,
	submitPaymentAttempt,
	submitRegistration,
	submitSavedRegistration,
	resumeRegistration
} from '$lib/api/registrations';
import type {
	PublicTournament,
	PublicTournamentGame,
	RegistrationRead,
	RegistrationPaymentSession
} from '$lib/api/types';
import { clearSession, getAccessToken } from '$lib/auth/session';
import { replaceInternalLocation } from '$lib/auth/navigation';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { DEFAULT_DISPLAY_TIME_ZONE } from '$lib/time/tournament-time';
import RegisterPage from './tournaments/[slug]/games/[gameId]/register/+page.svelte';

const mockPage = vi.hoisted(() => ({
	url: new URL('https://usec.test/tournaments/usec-summer-2026/games/10/register'),
	params: { id: '33' }
}));
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
vi.mock('$app/state', () => ({ page: mockPage }));
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
	resumeRegistration: vi.fn()
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
	vi.mocked(getRegistrationStorage).mockReturnValue(createRegistrationStorage());
	sessionStorage.clear();
	localStorage.clear();
	vi.mocked(submitSavedRegistration).mockReset().mockResolvedValue(registration);
	vi.mocked(resumeRegistration).mockReset();
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

async function chooseInstitution(index: number, label = 'HCMUS') {
	await page
		.getByLabelText(m.roster_first_name(), { exact: true })
		.nth(index)
		.fill(`Player ${index + 1}`);
	await page.getByLabelText('Last name', { exact: true }).nth(index).fill('Example');
	await page.getByLabelText('Date of birth', { exact: true }).nth(index).fill('01/01/2005');
	await page.getByRole('combobox', { name: 'Institution' }).nth(index).fill(label);
	await page.getByRole('button', { name: `Use "${label}"` }).click();
}

describe('registration stages', () => {
	it('keeps stepper keyboard navigation gated and updates the URL and active step together', async () => {
		mountGame();
		const details = page.getByRole('button', { name: '1. Team & contact', exact: true });
		const roster = page.getByRole('button', { name: '2. Roster', exact: true });
		const review = page.getByRole('button', { name: '3. Review registration', exact: true });
		await expect.element(roster).toBeDisabled();
		await expect.element(review).toBeDisabled();
		await details.click();
		await userEvent.keyboard('{ArrowRight}');
		await expect.element(details).toHaveAttribute('aria-current', 'step');
		await fillDetails();
		await details.click();
		await userEvent.keyboard('{ArrowRight}');
		await expect.element(roster).toHaveAttribute('aria-current', 'step');
		await expect.element(page.getByLabelText('Gamer tag').first()).toBeVisible();
		expect(vi.mocked(goto).mock.calls.at(-1)?.[0]).toContain('step=roster');
		await roster.click();
		await userEvent.keyboard('{ArrowRight}');
		await expect.element(roster).toHaveAttribute('aria-current', 'step');
		await userEvent.keyboard('{ArrowLeft}');
		await expect.element(details).toHaveAttribute('aria-current', 'step');
		await expect.element(page.getByLabelText('Team name')).toHaveValue('Blue Team');
		expect(vi.mocked(goto).mock.calls.at(-1)?.[0]).toContain('step=details');
	});

	it('validates details before showing roster and preserves both when navigating back', async () => {
		render(RegisterPage, {
			data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
			params: { slug: tournament.slug, gameId: '10' }
		});
		await expect.element(page.getByLabelText('Facebook', { exact: true })).toBeVisible();
		await expect.element(page.getByLabelText('Gamer tag')).not.toBeInTheDocument();
		await page.getByRole('button', { name: 'Continue', exact: true }).click();
		await expect.element(page.getByLabelText('Team name')).toHaveFocus();
		await page.getByLabelText('Team name').fill('Blue Team');
		await page.getByLabelText('Team tag', { exact: true }).fill('blue');
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/player');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByRole('button', { name: 'Continue', exact: true }).click();
		await page.getByLabelText('Gamer tag').nth(0).fill('captain');
		await chooseInstitution(0);
		await page.getByLabelText('Gamer tag').nth(1).fill('player');
		await chooseInstitution(1);
		await page.getByRole('button', { name: 'Back', exact: true }).click();
		await expect.element(page.getByLabelText('Team name')).toHaveValue('Blue Team');
		await page.getByRole('button', { name: 'Continue', exact: true }).click();
		await expect.element(page.getByLabelText('Gamer tag').nth(0)).toHaveValue('captain');
		await page.getByRole('button', { name: 'Continue', exact: true }).click();
		await expect
			.element(page.getByRole('heading', { name: 'Review registration', exact: true }))
			.toBeVisible();
		await expect
			.element(page.getByLabelText('Payment proof', { exact: true }))
			.not.toBeInTheDocument();
		await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/registrations/33/payment'));
		expect(submitSavedRegistration).toHaveBeenCalledOnce();
		expect(vi.mocked(submitSavedRegistration).mock.calls[0][1]).not.toHaveProperty(
			'payment_intent_token'
		);
		expect(vi.mocked(submitSavedRegistration).mock.calls[0][1]).not.toHaveProperty('proof_file');
		expect(localStorage.getItem('usec-registration-draft:v1:10')).toBeNull();
	});
});

async function fillDetails() {
	await page.getByLabelText('Team name').fill('Blue Team');
	await page.getByLabelText('Team tag', { exact: true }).fill('blue');
	await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/player');
	await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
}
function mountGame(overrides: Partial<PublicTournamentGame> = {}) {
	return render(RegisterPage, {
		data: {
			tournament,
			game: { ...game, ...overrides },
			displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE
		},
		params: { slug: tournament.slug, gameId: '10' }
	});
}
it('offers the latest saved draft without overwriting it before Continue and restores roster edits', async () => {
	const first = mountGame();
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await page.getByLabelText('Gamer tag').nth(0).fill('Unfinished player');
	await vi.waitFor(() =>
		expect(
			JSON.parse(localStorage.getItem('usec-registration-draft:v1:10')!).fields.members[0]
				.gamer_tag_snapshot
		).toBe('Unfinished player')
	);
	await first.unmount();
	const before = localStorage.getItem('usec-registration-draft:v1:10');
	mountGame();
	await expect.element(page.getByText('Continue your saved draft?')).toBeVisible();
	expect(localStorage.getItem('usec-registration-draft:v1:10')).toBe(before);
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByLabelText('Gamer tag').nth(0)).toHaveValue('Unfinished player');
	await page.getByRole('button', { name: 'Back', exact: true }).click();
	await expect.element(page.getByLabelText('Team name')).toHaveValue('Blue Team');
});
it('clears saved progress without immediately recreating it', async () => {
	mountGame();
	await fillDetails();
	await vi.waitFor(() =>
		expect(localStorage.getItem('usec-registration-draft:v1:10')).not.toBeNull()
	);
	await page.getByRole('button', { name: 'Clear saved progress' }).click();
	await new Promise((resolve) => setTimeout(resolve, 400));
	expect(localStorage.getItem('usec-registration-draft:v1:10')).toBeNull();
});
it('does not permit a direct future-stage URL with an empty form', async () => {
	mockPage.url = new URL('https://usec.test/tournaments/summer/games/10/register?step=review');
	mountGame();
	await expect.element(page.getByLabelText('Team name')).toBeVisible();
	await expect
		.element(page.getByRole('heading', { name: 'Review registration', exact: true }))
		.not.toBeInTheDocument();
});
it('keeps multiple saved submissions available when the division is closed', async () => {
	for (const [id, key] of [
		[33, 'ab'],
		[34, 'cd']
	] as const)
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
	mountGame({ is_registration_open: false, capacity_remaining: 0 });
	await expect
		.element(page.getByRole('link', { name: 'View registration 33 / payment' }))
		.toBeVisible();
	await expect
		.element(page.getByRole('link', { name: 'View registration 34 / payment' }))
		.toBeVisible();
});
it('requires Turnstile only at review and keeps fields after authoritative roster errors', async () => {
	vi.mocked(submitSavedRegistration).mockRejectedValue(
		new ApiRequestError(400, 'Invalid', { members: ['Roster invalid.'] })
	);
	mountGame();
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	for (let i = 0; i < 2; i++) {
		await page.getByLabelText('Gamer tag').nth(i).fill(`player${i}`);
		await chooseInstitution(i);
	}
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await expect.element(page.getByText('Roster invalid.').first()).toBeVisible();
	await expect.element(page.getByLabelText('Gamer tag').nth(0)).toHaveValue('player0');
});
it('resumes a lost response with its saved credential before permitting another submission', async () => {
	vi.mocked(submitSavedRegistration).mockRejectedValue(new Error('Lost response'));
	vi.mocked(resumeRegistration).mockRejectedValue(new ApiRequestError(404, 'Missing'));
	mountGame();
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	for (let i = 0; i < 2; i++) {
		await page.getByLabelText('Gamer tag').nth(i).fill(`player${i}`);
		await chooseInstitution(i);
	}
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await expect
		.element(page.getByRole('button', { name: 'Recover pending submission' }).last())
		.toBeVisible();
	await page.getByRole('button', { name: 'Recover pending submission' }).last().click();
	await vi.waitFor(() => expect(resumeRegistration).toHaveBeenCalled());
	expect(vi.mocked(resumeRegistration).mock.calls[0][0]).toBe(
		vi.mocked(submitSavedRegistration).mock.calls[0][3]
	);
});

it('submits a free manager with the chosen captain and saves confirmation without payment navigation', async () => {
	vi.mocked(submitSavedRegistration).mockResolvedValue({
		...registration,
		payment_required: false,
		payment_state: 'NOT_REQUIRED',
		payment_due_at: null
	});
	mountGame({ fee_amount: '0.00' });
	await page.getByRole('radio', { name: 'Manager', exact: true }).click();
	await page.getByLabelText('Manager name').fill('Coach');
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	for (let i = 0; i < 2; i++) {
		await page.getByLabelText('Gamer tag').nth(i).fill(`player${i}`);
		await chooseInstitution(i);
	}
	await page.getByRole('radio', { name: 'Set member 2 as captain' }).click();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByText('Coach', { exact: true })).toBeVisible();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await expect.element(page.getByRole('heading', { name: 'Registration submitted' })).toBeVisible();
	expect(vi.mocked(submitSavedRegistration).mock.calls[0][1].members[1].is_captain).toBe(true);
	expect(goto).not.toHaveBeenCalledWith('/en/registrations/33/payment');
	window.dispatchEvent(new Event('pagehide'));
	expect(localStorage.getItem('usec-registration-draft:v1:10')).toBeNull();
});
it('preserves surplus restored mains and permits explicit removal after roster rules change', async () => {
	const first = mountGame();
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await page.getByLabelText('Gamer tag').nth(1).fill('Extra player');
	await first.unmount();
	mountGame({ main_roster_size: 1 });
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByLabelText('Gamer tag').nth(1)).toHaveValue('Extra player');
	await page.getByRole('button', { name: 'Remove member 2' }).click();
	await expect.element(page.getByLabelText('Gamer tag')).toBeVisible();
});
it('renders Vietnamese stage navigation', async () => {
	overwriteGetLocale(() => 'vi');
	mountGame();
	await expect.element(page.getByRole('button', { name: 'Tiếp tục', exact: true })).toBeVisible();
});

it('renders a warning for a late quota failure and keeps current draft values', async () => {
	mountGame();
	await fillDetails();
	await vi.waitFor(() =>
		expect(localStorage.getItem('usec-registration-draft:v1:10')).not.toBeNull()
	);
	const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
		throw new DOMException('Quota exceeded', 'QuotaExceededError');
	});
	try {
		await page.getByLabelText('Team name').fill('New local team');
		await expect
			.element(page.getByText(/Storage is unavailable. Keep this tab open/))
			.toBeVisible();
		await expect.element(page.getByLabelText('Team name')).toHaveValue('New local team');
	} finally {
		write.mockRestore();
	}
});

it('isolates two divisions on the same page and flushes the departing draft under its original ID', async () => {
	const view = mountGame();
	await fillDetails();
	window.dispatchEvent(new Event('pagehide'));
	const original = JSON.parse(localStorage.getItem('usec-registration-draft:v1:10')!);
	localStorage.setItem(
		'usec-registration-draft:v1:11',
		JSON.stringify({
			...original,
			gameId: 11,
			fields: { ...original.fields, tournament_game: 11, team_name: 'Second division team' }
		})
	);
	await page.getByLabelText('Team name').fill('First division latest');
	await view.rerender({
		data: { tournament, game: { ...game, id: 11 }, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
		params: { slug: tournament.slug, gameId: '11' }
	});
	await expect.element(page.getByText('Continue your saved draft?')).toBeVisible();
	expect(JSON.parse(localStorage.getItem('usec-registration-draft:v1:10')!).fields.team_name).toBe(
		'First division latest'
	);
	expect(JSON.parse(localStorage.getItem('usec-registration-draft:v1:11')!).fields.team_name).toBe(
		'Second division team'
	);
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByLabelText('Team name')).toHaveValue('Second division team');
	await view.rerender({
		data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
		params: { slug: tournament.slug, gameId: '10' }
	});
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByLabelText('Team name')).toHaveValue('First division latest');
});
it('keeps a late submission result scoped to its departing division without redirecting the next division', async () => {
	let finish!: (registration: RegistrationRead) => void;
	vi.mocked(submitSavedRegistration).mockImplementation(
		() =>
			new Promise((resolve) => {
				finish = resolve;
			})
	);
	const view = mountGame();
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	for (let index = 0; index < 2; index++) {
		await page.getByLabelText('Gamer tag').nth(index).fill(`player${index}`);
		await chooseInstitution(index);
	}
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await vi.waitFor(() => expect(submitSavedRegistration).toHaveBeenCalledOnce());
	await view.rerender({
		data: { tournament, game: { ...game, id: 11 }, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
		params: { slug: tournament.slug, gameId: '11' }
	});
	await expect.element(page.getByLabelText('Team name')).toHaveValue('');
	vi.mocked(goto).mockClear();
	finish(registration);
	await vi.waitFor(() => expect(localStorage.getItem('usec-registration-draft:v1:10')).toBeNull());
	expect(goto).not.toHaveBeenCalled();
	await expect.element(page.getByLabelText('Team name')).toHaveValue('');
});
it('preserves dirty team identity when navigating to a solo division with its own saved draft', async () => {
	const view = mountGame();
	await fillDetails();
	window.dispatchEvent(new Event('pagehide'));
	const original = JSON.parse(localStorage.getItem('usec-registration-draft:v1:10')!);
	const soloDraft = JSON.stringify({
		...original,
		gameId: 11,
		fields: {
			...original.fields,
			tournament_game: 11,
			team_name: '',
			team_tag: '',
			contact_facebook_snapshot: 'facebook.com/solo-player'
		}
	});
	localStorage.setItem('usec-registration-draft:v1:11', soloDraft);
	await page.getByLabelText('Team name').fill('Dirty departing team');
	await page.getByLabelText('Team tag', { exact: true }).fill('LATE');
	await view.rerender({
		data: {
			tournament,
			game: { ...game, id: 11, main_roster_size: 1, substitute_limit: 0 },
			displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE
		},
		params: { slug: tournament.slug, gameId: '11' }
	});
	await expect.element(page.getByText('Continue your saved draft?')).toBeVisible();
	const savedTeam = JSON.parse(localStorage.getItem('usec-registration-draft:v1:10')!);
	expect(savedTeam.fields.team_name).toBe('Dirty departing team');
	expect(savedTeam.fields.team_tag).toBe('LATE');
	expect(localStorage.getItem('usec-registration-draft:v1:11')).toBe(soloDraft);
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByLabelText('Team name')).not.toBeInTheDocument();
	await expect
		.element(page.getByLabelText('Facebook', { exact: true }))
		.toHaveValue('facebook.com/solo-player');
	await view.rerender({
		data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
		params: { slug: tournament.slug, gameId: '10' }
	});
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByLabelText('Team name')).toHaveValue('Dirty departing team');
	await expect.element(page.getByLabelText('Team tag', { exact: true })).toHaveValue('LATE');
});
import RegistrationWizard from '$lib/components/registrations/RegistrationWizard.svelte';
it('flushes original instance rules even if incoming props change before wizard teardown', async () => {
	const view = render(RegistrationWizard, { data: { tournament, game } });
	await fillDetails();
	await page.getByLabelText('Team name').fill('Unflushed team');
	await page.getByLabelText('Team tag', { exact: true }).fill('KEEP');
	await view.rerender({
		data: { tournament, game: { ...game, id: 11, main_roster_size: 1, substitute_limit: 0 } }
	});
	window.dispatchEvent(new Event('pagehide'));
	const oldDraft = JSON.parse(localStorage.getItem('usec-registration-draft:v1:10')!);
	expect(oldDraft.fields.team_name).toBe('Unflushed team');
	expect(oldDraft.fields.team_tag).toBe('KEEP');
	expect(localStorage.getItem('usec-registration-draft:v1:11')).toBeNull();
});

const legacyKey = 'usec-payment-intent:10';
const legacyToken = 'old-possibly-paid-token';
const unpaidChoice = 'I haven’t paid — start a new registration';
const legacyGuidance =
	'This tab has earlier payment instructions. If you already transferred, contact the organizers with your proof instead of paying again. If you have not paid, explicitly start a new registration below. Saved submissions can still be recovered.';
async function completeReview() {
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	for (let index = 0; index < 2; index++) {
		await page.getByLabelText('Gamer tag').nth(index).fill(`legacy-player${index}`);
		await chooseInstitution(index);
	}
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
}
function recoveredSession(): RegistrationPaymentSession {
	return { registration } as RegistrationPaymentSession;
}

it('guards the real route with organizer guidance before any fresh submission and retains failed legacy replacement', async () => {
	sessionStorage.setItem(legacyKey, legacyToken);
	vi.mocked(submitSavedRegistration).mockRejectedValue(
		new ApiRequestError(400, 'Invalid', { members: ['Roster invalid.'] })
	);
	mountGame();
	await expect.element(page.getByText(legacyGuidance)).toBeVisible();
	await expect.element(page.getByLabelText('Team name')).not.toBeInTheDocument();
	expect(submitSavedRegistration).not.toHaveBeenCalled();
	await page.getByRole('button', { name: unpaidChoice }).click();
	await completeReview();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await expect.element(page.getByText('Roster invalid.').first()).toBeVisible();
	expect(sessionStorage.getItem(legacyKey)).toBe(legacyToken);
});

it('clears only the old division token after the explicit fresh flow succeeds without sending old proof or token', async () => {
	sessionStorage.setItem(legacyKey, legacyToken);
	sessionStorage.setItem('usec-payment-intent:11', 'other-token');
	mountGame();
	await page.getByRole('button', { name: unpaidChoice }).click();
	await completeReview();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/registrations/33/payment'));
	expect(sessionStorage.getItem(legacyKey)).toBeNull();
	expect(sessionStorage.getItem('usec-payment-intent:11')).toBe('other-token');
	const submitted = vi.mocked(submitSavedRegistration).mock.calls[0][1];
	expect(submitted).not.toHaveProperty('payment_intent_token');
	expect(submitted).not.toHaveProperty('proof_file');
});

it('does not carry an unpaid decision across reload or division navigation', async () => {
	sessionStorage.setItem(legacyKey, legacyToken);
	sessionStorage.setItem('usec-payment-intent:11', 'other-token');
	const first = mountGame();
	await page.getByRole('button', { name: unpaidChoice }).click();
	await first.unmount();
	const second = mountGame();
	await expect.element(page.getByText(legacyGuidance)).toBeVisible();
	await page.getByRole('button', { name: unpaidChoice }).click();
	await second.rerender({
		data: { tournament, game: { ...game, id: 11 }, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
		params: { slug: tournament.slug, gameId: '11' }
	});
	await expect.element(page.getByText(legacyGuidance)).toBeVisible();
	await second.rerender({
		data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
		params: { slug: tournament.slug, gameId: '10' }
	});
	await expect.element(page.getByText(legacyGuidance)).toBeVisible();
	expect(sessionStorage.getItem(legacyKey)).toBe(legacyToken);
	expect(submitSavedRegistration).not.toHaveBeenCalled();
});

it.each([false, true])(
	'retains an uncertain legacy flow until confirmed recovery, with reload=%s',
	async (reload) => {
		sessionStorage.setItem(legacyKey, legacyToken);
		vi.mocked(submitSavedRegistration).mockRejectedValue(new Error('Lost response'));
		vi.mocked(resumeRegistration).mockResolvedValue(recoveredSession());
		const first = mountGame();
		await page.getByRole('button', { name: unpaidChoice }).click();
		await completeReview();
		await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
		await expect
			.element(page.getByRole('button', { name: 'Recover pending submission' }).first())
			.toBeVisible();
		expect(sessionStorage.getItem(legacyKey)).toBe(legacyToken);
		if (reload) {
			await first.unmount();
			mountGame();
			await expect.element(page.getByText(legacyGuidance)).toBeVisible();
		}
		await page.getByRole('button', { name: 'Recover pending submission' }).first().click();
		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/registrations/33/payment'));
		expect(submitSavedRegistration).toHaveBeenCalledOnce();
		expect(sessionStorage.getItem(legacyKey)).toBe(reload ? legacyToken : null);
	}
);

it.each([false, true])(
	'allows read-only recovery but guards a missing submission replay after reload, lost replay=%s',
	async (lostReplay) => {
		sessionStorage.setItem(legacyKey, legacyToken);
		vi.mocked(submitSavedRegistration).mockRejectedValue(new Error('Lost response'));
		vi.mocked(resumeRegistration).mockRejectedValue(new ApiRequestError(404, 'Missing'));
		const first = mountGame();
		await page.getByRole('button', { name: unpaidChoice }).click();
		await completeReview();
		await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
		await expect
			.element(page.getByRole('button', { name: 'Recover pending submission' }).first())
			.toBeVisible();
		await first.unmount();
		localStorage.removeItem('usec-registration-draft:v1:10');
		mountGame();
		await page.getByRole('button', { name: 'Recover pending submission' }).first().click();
		await vi.waitFor(() => expect(resumeRegistration).toHaveBeenCalledOnce());
		expect(submitSavedRegistration).toHaveBeenCalledOnce();
		expect(sessionStorage.getItem(legacyKey)).toBe(legacyToken);
		await page.getByRole('button', { name: unpaidChoice }).click();
		if (lostReplay)
			vi.mocked(submitSavedRegistration).mockRejectedValue(new Error('Lost replay response'));
		else vi.mocked(submitSavedRegistration).mockResolvedValue(registration);
		await page.getByRole('button', { name: 'Recover pending submission' }).last().click();
		await vi.waitFor(() => expect(submitSavedRegistration).toHaveBeenCalledTimes(2));
		if (lostReplay) {
			expect(sessionStorage.getItem(legacyKey)).toBe(legacyToken);
			vi.mocked(resumeRegistration).mockResolvedValue(recoveredSession());
			await page.getByRole('button', { name: 'Recover pending submission' }).last().click();
		}
		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/registrations/33/payment'));
		expect(sessionStorage.getItem(legacyKey)).toBe(lostReplay ? legacyToken : null);
	}
);

it('does not erase a changed legacy token when the explicitly chosen submission finishes', async () => {
	sessionStorage.setItem(legacyKey, legacyToken);
	vi.mocked(submitSavedRegistration).mockImplementation(async () => {
		sessionStorage.setItem(legacyKey, 'newer-token');
		return registration;
	});
	mountGame();
	await page.getByRole('button', { name: unpaidChoice }).click();
	await completeReview();
	await page.getByRole('button', { name: 'Submit registration', exact: true }).click();
	await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/registrations/33/payment'));
	expect(sessionStorage.getItem(legacyKey)).toBe('newer-token');
});

it('retains an old quote when an unrelated saved entry resumes even after an unpaid choice', async () => {
	sessionStorage.setItem(legacyKey, legacyToken);
	const credential = 'ab'.repeat(32);
	localStorage.setItem(
		`usec-registration-access:v1:${credential}`,
		JSON.stringify({
			version: 1,
			gameId: 10,
			credential,
			attemptState: 'uncertain',
			registrationId: null,
			actorId: null,
			submittedPayload: {
				tournament_game: 10,
				team_name: 'Earlier team',
				team_tag: 'OLD',
				submitter_role: 'captain',
				contact_facebook_snapshot: 'facebook.com/earlier',
				contact_phone_snapshot: '0901234567',
				members: []
			}
		})
	);
	vi.mocked(resumeRegistration).mockResolvedValue(recoveredSession());
	mountGame();
	await page.getByRole('button', { name: unpaidChoice }).click();
	await page.getByRole('button', { name: 'Recover pending submission' }).first().click();
	await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/en/registrations/33/payment'));
	expect(submitSavedRegistration).not.toHaveBeenCalled();
	expect(sessionStorage.getItem(legacyKey)).toBe(legacyToken);
});

it.each([
	['not_open', false, null, 'Registration for this division has not opened yet.'],
	['closed', false, null, 'Registration for this division has closed.'],
	['full', true, null, 'This division is full.'],
	['open', true, 0, 'This division is full.'],
	[
		'open',
		true,
		null,
		'Payment is not ready for this division. Please contact the organizers before registering.'
	]
] as const)(
	'explains availability for state=%s open=%s capacity=%s',
	async (state, open, capacity, message) => {
		mountGame({
			registration_state: state,
			is_registration_open: open,
			capacity_remaining: capacity,
			payment_available: false
		});
		await expect
			.element(page.getByText(m.registration_loading(), { exact: true }))
			.not.toBeInTheDocument();
		expect(document.body.textContent).toContain(message);
		await expect.element(page.getByLabelText('Team name')).not.toBeInTheDocument();
		expect(submitSavedRegistration).not.toHaveBeenCalled();
	}
);

it('explains payment availability in Vietnamese without claiming registration is closed', async () => {
	overwriteGetLocale(() => 'vi');
	mountGame({ payment_available: false });
	await expect
		.element(page.getByText(m.registration_loading(), { exact: true }))
		.not.toBeInTheDocument();
	expect(document.body.textContent).toContain(
		'Thanh toán cho nội dung này chưa sẵn sàng. Vui lòng liên hệ ban tổ chức trước khi đăng ký.'
	);
});

it('keeps free registration available when payment setup is unavailable', async () => {
	mountGame({ fee_amount: '0.00', payment_available: false });
	await expect.element(page.getByLabelText('Team name')).toBeVisible();
	await fillDetails();
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect.element(page.getByLabelText('Gamer tag').first()).toBeVisible();
});

it('keeps saved access and draft restoration ahead of the payment availability notice', async () => {
	const first = mountGame();
	await fillDetails();
	await first.unmount();
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
	const draft = localStorage.getItem('usec-registration-draft:v1:10');
	mountGame({ payment_available: false });
	await expect
		.element(page.getByRole('link', { name: 'View registration 33 / payment' }))
		.toBeVisible();
	await expect.element(page.getByText('Continue your saved draft?')).toBeVisible();
	expect(localStorage.getItem('usec-registration-draft:v1:10')).toBe(draft);
	await page.getByRole('button', { name: 'Continue', exact: true }).click();
	await expect
		.element(
			page.getByText(
				'Payment is not ready for this division. Please contact the organizers before registering.',
				{ exact: true }
			)
		)
		.toBeVisible();
});
