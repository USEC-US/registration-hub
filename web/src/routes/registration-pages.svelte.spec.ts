import * as m from '$lib/paraglide/messages';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { page as appPage } from '$app/state';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { ApiRequestError } from '$lib/api/client';
import {
	getRegistration,
	listRegistrations,
	submitPaymentAttempt,
	submitRegistration
} from '$lib/api/registrations';
import type { PublicTournament, PublicTournamentGame, RegistrationRead } from '$lib/api/types';
import { clearSession, getAccessToken } from '$lib/auth/session';
import { replaceInternalLocation } from '$lib/auth/navigation';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { DEFAULT_DISPLAY_TIME_ZONE } from '$lib/time/tournament-time';
import RegistrationsPage from './account/registrations/+page.svelte';
import RegistrationDetailPage from './account/registrations/[id]/+page.svelte';
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
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/state', () => ({ page: mockPage }));
vi.mock('$lib/api/registrations', () => ({
	reservePaymentReference: vi.fn().mockResolvedValue({
		token: 'payment-token',
		reference: 'USEC23456789AB',
		amount: '50000.00',
		currency: 'VND'
	}),
	getPaymentReference: vi.fn().mockResolvedValue({ reference: 'USEC23456789AB' }),
	getRegistration: vi.fn(),
	listRegistrations: vi.fn(),
	submitPaymentAttempt: vi.fn(),
	submitRegistration: vi.fn()
}));
vi.mock('$lib/auth/session', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/auth/session')>()),
	getAccessToken: vi.fn(),
	clearSession: vi.fn()
}));
vi.mock('$lib/api/institutions', () => ({ searchInstitutions: vi.fn().mockResolvedValue([]) }));
vi.mock('$lib/auth/navigation', () => ({ replaceInternalLocation: vi.fn() }));

const accessToken = 'access-token';
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
	is_registration_open: true
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
	overwriteGetLocale(() => 'en');
	mockPage.url = new URL('https://usec.test/tournaments/usec-summer-2026/games/10/register');
	mockPage.params = { id: '33' };
	vi.mocked(goto).mockReset().mockResolvedValue(undefined);
	vi.mocked(getAccessToken).mockReset().mockReturnValue(accessToken);
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

describe('participant registration pages', () => {
	it('requires guest payment proof and preserves fields after an invalid image', async () => {
		vi.mocked(getAccessToken).mockReturnValue(null);
		render(RegisterPage, {
			data: {
				tournament,
				game: { ...game, main_roster_size: 1, substitute_limit: 0 },
				displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE
			},
			params: { slug: tournament.slug, gameId: String(game.id) }
		});
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/player');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByLabelText('Gamer tag').fill('player#123');
		await chooseInstitution(0);
		await page.getByRole('button', { name: 'Submit registration' }).click();
		await expect.element(page.getByText('Upload a payment proof image.')).toBeVisible();
		expect(submitRegistration).not.toHaveBeenCalled();
		const input = document.querySelector<HTMLInputElement>('input[type=file]')!;
		const invalid = new DataTransfer();
		invalid.items.add(new File(['pdf'], 'proof.pdf', { type: 'application/pdf' }));
		input.files = invalid.files;
		input.dispatchEvent(new Event('change', { bubbles: true }));
		await page.getByRole('button', { name: 'Submit registration' }).click();
		await expect.element(page.getByLabelText('Gamer tag')).toHaveValue('player#123');
		expect(submitRegistration).not.toHaveBeenCalled();
		const valid = new DataTransfer();
		valid.items.add(new File(['image'], 'proof.png', { type: 'image/png' }));
		input.files = valid.files;
		input.dispatchEvent(new Event('change', { bubbles: true }));
		await expect.element(page.getByLabelText('Payment reference')).toHaveAttribute('readonly');
		await page.getByRole('button', { name: 'Submit registration' }).click();
		await expect
			.element(page.getByRole('heading', { name: 'Registration submitted' }))
			.toBeVisible();
		const [token, payload, challenge, proof, reference] =
			vi.mocked(submitRegistration).mock.calls[0];
		expect(token).toBeNull();
		expect(payload.team_name).toBe('');
		expect(challenge).toBe('registration-submit-token');
		expect(proof?.name).toBe('proof.png');
		expect(reference).toBeUndefined();
		expect(payload.payment_intent_token).toBe('payment-token');
	});

	it('blocks an invalid optional proof until a signed-in player removes it', async () => {
		vi.mocked(getAccessToken).mockReturnValue('access-token');
		render(RegisterPage, {
			data: {
				tournament,
				game: { ...game, main_roster_size: 1, substitute_limit: 0 },
				displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE
			},
			params: { slug: tournament.slug, gameId: String(game.id) }
		});
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/player');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByLabelText('Gamer tag').fill('player#123');
		await chooseInstitution(0);
		const input = document.querySelector<HTMLInputElement>('input[type=file]')!;
		const transfer = new DataTransfer();
		transfer.items.add(new File(['pdf'], 'proof.pdf', { type: 'application/pdf' }));
		input.files = transfer.files;
		input.dispatchEvent(new Event('change', { bubbles: true }));
		await page.getByRole('button', { name: 'Submit registration' }).click();
		await expect
			.element(page.getByText('Choose a JPEG, PNG, or WebP image no larger than 10 MB.'))
			.toBeVisible();
		expect(submitRegistration).not.toHaveBeenCalled();
		await page.getByRole('button', { name: 'Remove image', exact: true }).click();
		await page.getByRole('button', { name: 'Submit registration' }).click();
		await vi.waitFor(() => expect(submitRegistration).toHaveBeenCalledOnce());
		expect(vi.mocked(submitRegistration).mock.calls[0][3]).toBeUndefined();
	});

	it('submits a free guest manager with a separate name and confirms organizer corrections', async () => {
		vi.mocked(getAccessToken).mockReturnValue(null);
		const { container } = render(RegisterPage, {
			data: {
				tournament,
				game: { ...game, fee_amount: '0.00' },
				displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE
			},
			params: { slug: tournament.slug, gameId: String(game.id) }
		});
		await page.getByRole('radio', { name: 'Manager', exact: true }).click();
		await page.getByLabelText('Manager name').fill('Coach');
		await page.getByLabelText('Team name').fill('Guest team');
		await page.getByLabelText('Team tag', { exact: true }).fill('blue');
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/coach');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByLabelText('Gamer tag').nth(0).fill('player1');
		await chooseInstitution(0);
		await page.getByLabelText('Gamer tag').nth(1).fill('player2');
		await chooseInstitution(1);
		await page.getByRole('radio', { name: 'Set member 2 as captain' }).click();
		expect(container.querySelector('input[type=file]')).toBeNull();
		await page.getByRole('button', { name: 'Submit registration' }).click();
		await expect
			.element(page.getByRole('heading', { name: 'Registration submitted' }))
			.toBeVisible();
		await expect.element(page.getByText('Registration reference: 33')).toBeVisible();
		await expect.element(page.getByText(/contact the organizers/i)).toBeVisible();
		expect(goto).not.toHaveBeenCalled();
		const [token, payload] = vi.mocked(submitRegistration).mock.calls[0];
		expect(token).toBeNull();
		expect(payload).toMatchObject({
			submitter_role: 'manager',
			manager_name_snapshot: 'Coach',
			contact_email_snapshot: '',
			contact_discord_snapshot: ''
		});
		expect(payload.members).toHaveLength(2);
		expect(payload.members[1].is_captain).toBe(true);
	});

	it('keeps guests on the shared form and locks the captain in slot one', async () => {
		vi.mocked(getAccessToken).mockReturnValue(null);
		render(RegisterPage, {
			data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
			params: { slug: tournament.slug, gameId: String(game.id) }
		});
		await expect.element(page.getByRole('button', { name: 'Submit registration' })).toBeVisible();
		expect(replaceInternalLocation).not.toHaveBeenCalled();
		await expect
			.element(page.getByRole('radio', { name: 'Set member 2 as captain' }))
			.toBeDisabled();
		await expect.element(page.getByLabelText('Facebook', { exact: true })).toBeRequired();
		await expect.element(page.getByLabelText('Phone', { exact: true })).toBeRequired();
		await page.getByRole('radio', { name: 'Manager', exact: true }).click();
		await expect.element(page.getByLabelText('Manager name')).toBeRequired();
		await page.getByRole('radio', { name: 'Set member 2 as captain' }).click();
		await expect
			.element(page.getByRole('radio', { name: 'Set member 2 as captain' }))
			.toBeChecked();
		await page.getByRole('radio', { name: 'Captain', exact: true }).click();
		await expect
			.element(page.getByRole('radio', { name: 'Set member 1 as captain' }))
			.toBeChecked();
	});

	it('starts with an empty roster and submits the bound team roster', async () => {
		const { container } = render(RegisterPage, {
			data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
			params: { slug: tournament.slug, gameId: String(game.id) }
		});

		await vi.waitFor(() =>
			expect(container.querySelector('input[name="member-1-gamer-tag"]')).toHaveValue('')
		);
		expect(container.querySelector('[data-slot="card"]')).not.toBeNull();
		expect(container.querySelector('button[type="submit"]')).toHaveAttribute('data-slot', 'button');
		expect(container.querySelector('input[name="institution"]')).toHaveValue('');
		await page.getByLabelText('Team name').fill('Blue Team');
		await page.getByLabelText('Team tag', { exact: true }).fill('blue');
		await page.getByLabelText('Gamer tag').nth(0).fill('captain');
		await chooseInstitution(0);
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/captain');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByLabelText('Gamer tag').nth(1).fill('teammate');
		await chooseInstitution(1);
		await page.getByRole('button', { name: 'Submit registration' }).click();

		await vi.waitFor(() =>
			expect(submitRegistration).toHaveBeenCalledWith(
				accessToken,
				{
					tournament_game: 10,
					payment_intent_token: 'payment-token',
					team_name: 'Blue Team',
					team_tag: 'BLUE',
					submitter_role: 'captain',
					manager_name_snapshot: '',
					contact_facebook_snapshot: 'facebook.com/captain',
					contact_phone_snapshot: '0901234567',
					contact_email_snapshot: '',
					contact_discord_snapshot: '',
					members: [
						{
							gamer_tag_snapshot: 'captain',
							first_name_snapshot: 'Player 1',
							last_name_snapshot: 'Example',
							date_of_birth_snapshot: '2005-01-01',
							student_id_snapshot: '',
							institution_label: 'HCMUS',
							roster_role: 'main',
							is_captain: true,
							display_order: 1
						},
						{
							gamer_tag_snapshot: 'teammate',
							first_name_snapshot: 'Player 2',
							last_name_snapshot: 'Example',
							date_of_birth_snapshot: '2005-01-01',
							student_id_snapshot: '',
							institution_label: 'HCMUS',
							roster_role: 'main',
							is_captain: false,
							display_order: 2
						}
					]
				},
				'registration-submit-token',
				undefined
			)
		);
		expect(goto).toHaveBeenCalledWith('/en/account/registrations/33');
	});

	it('shows roster validation errors returned by the registration API', async () => {
		vi.mocked(submitRegistration).mockRejectedValue(
			new ApiRequestError(400, 'Request failed.', { members: ['Roster invalid.'] })
		);
		render(RegisterPage, {
			data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
			params: { slug: tournament.slug, gameId: String(game.id) }
		});

		await expect.element(page.getByLabelText('Team name')).toBeInTheDocument();
		await page.getByLabelText('Team name').fill('Blue Team');
		await page.getByLabelText('Team tag', { exact: true }).fill('blue');
		await page.getByLabelText('Gamer tag').nth(0).fill('captain');
		await chooseInstitution(0);
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/captain');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByLabelText('Gamer tag').nth(1).fill('teammate');
		await chooseInstitution(1);
		await page.getByRole('button', { name: 'Submit registration' }).click();

		await expect.element(page.getByText('Roster invalid.')).toBeInTheDocument();
	});

	it('requires Turnstile before submitting tournament registration', async () => {
		turnstileTokens['registration-submit'] = '';
		render(RegisterPage, {
			data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
			params: { slug: tournament.slug, gameId: String(game.id) }
		});

		await page.getByLabelText('Team name').fill('Blue Team');
		await page.getByLabelText('Team tag', { exact: true }).fill('blue');
		await page.getByLabelText('Gamer tag').nth(0).fill('captain');
		await chooseInstitution(0);
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/captain');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByLabelText('Gamer tag').nth(1).fill('teammate');
		await chooseInstitution(1);
		await page.getByRole('button', { name: 'Submit registration' }).click();

		await expect
			.element(page.getByText('Complete the security check before submitting.'))
			.toBeVisible();
		expect(submitRegistration).not.toHaveBeenCalled();
	});

	it('requires a fresh Turnstile callback before retrying tournament registration', async () => {
		vi.mocked(submitRegistration).mockRejectedValue(new Error('Request failed.'));
		render(RegisterPage, {
			data: { tournament, game, displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE },
			params: { slug: tournament.slug, gameId: String(game.id) }
		});

		await page.getByLabelText('Team name').fill('Blue Team');
		await page.getByLabelText('Team tag', { exact: true }).fill('blue');
		await page.getByLabelText('Gamer tag').nth(0).fill('captain');
		await chooseInstitution(0);
		await page.getByLabelText('Facebook', { exact: true }).fill('facebook.com/captain');
		await page.getByLabelText('Phone', { exact: true }).fill('0901234567');
		await page.getByLabelText('Gamer tag').nth(1).fill('teammate');
		await chooseInstitution(1);
		await page.getByRole('button', { name: 'Submit registration' }).click();

		await vi.waitFor(() => expect(submitRegistration).toHaveBeenCalledOnce());
		expect(turnstileDependencies.reset).toHaveBeenCalledWith('widget-id');
		await page.getByRole('button', { name: 'Submit registration' }).click();

		await expect
			.element(page.getByText('Complete the security check before submitting.'))
			.toBeVisible();
		expect(submitRegistration).toHaveBeenCalledOnce();
	});

	it('lists registration snapshots with links to their details', async () => {
		mockPage.url = new URL('https://usec.test/account/registrations');
		const { container } = render(RegistrationsPage);

		await expect.element(page.getByText(tournament.name)).toBeInTheDocument();
		await expect.element(page.getByText(game.game_name)).toBeInTheDocument();
		await expect.element(page.getByText('Submitted', { exact: true }).first()).toBeInTheDocument();
		expect(container.querySelector('[data-slot="card"]')).not.toBeNull();
		expect(container.querySelector('[data-slot="badge"]')).not.toBeNull();
		expect(container.querySelector('a[href="/en/account/registrations/33"]')).not.toBeNull();
		await expect.element(page.getByText(/50,000/)).toBeInTheDocument();
	});

	it('renders registration detail and refreshes it after payment submission', async () => {
		mockPage.url = new URL('https://usec.test/account/registrations/33');
		const { container } = render(RegistrationDetailPage);

		await expect.element(page.getByText('teammate')).toBeInTheDocument();
		expect(container.querySelector('[data-slot="card"]')).not.toBeNull();
		expect(container.querySelector('[data-slot="badge"]')).not.toBeNull();
		await expect
			.element(page.getByRole('list', { name: 'Registration status timeline' }))
			.toBeInTheDocument();
		const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!;
		const transfer = new DataTransfer();
		transfer.items.add(new File(['proof'], 'proof.png', { type: 'image/png' }));
		fileInput.files = transfer.files;
		fileInput.dispatchEvent(new Event('change', { bubbles: true }));
		await expect.element(page.getByLabelText('Payment reference')).toHaveAttribute('readonly');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(getRegistration).toHaveBeenCalledTimes(2));
		expect(submitPaymentAttempt).toHaveBeenCalledWith(
			accessToken,
			registration.id,
			expect.any(FormData),
			'payment-proof-submit-token'
		);
		expect(appPage.params.id).toBe('33');
	});

	it('clears an expired session and redirects after payment submission', async () => {
		mockPage.url = new URL('https://usec.test/account/registrations/33');
		vi.mocked(submitPaymentAttempt).mockRejectedValue(
			new ApiRequestError(401, 'Authentication credentials were not provided.')
		);
		render(RegistrationDetailPage);

		await expect.element(page.getByLabelText('Payment reference')).toBeInTheDocument();
		const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!;
		const transfer = new DataTransfer();
		transfer.items.add(new File(['proof'], 'proof.png', { type: 'image/png' }));
		fileInput.files = transfer.files;
		fileInput.dispatchEvent(new Event('change', { bubbles: true }));
		await expect.element(page.getByLabelText('Payment reference')).toHaveAttribute('readonly');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(clearSession).toHaveBeenCalledOnce());
		expect(replaceInternalLocation).toHaveBeenCalledWith(
			'/en/auth/sign-in?redirect=%2Faccount%2Fregistrations%2F33'
		);
	});
});
