import { beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { page as appPage } from '$app/state';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { getCurrentUser } from '$lib/api/auth';
import { ApiRequestError } from '$lib/api/client';
import {
	getRegistration,
	listRegistrations,
	submitPaymentAttempt,
	submitRegistration
} from '$lib/api/registrations';
import type {
	CurrentUser,
	PublicTournament,
	PublicTournamentGame,
	RegistrationRead
} from '$lib/api/types';
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

vi.mock('$env/dynamic/public', () => ({ env: {} }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/state', () => ({ page: mockPage }));
vi.mock('$lib/api/auth', () => ({ getCurrentUser: vi.fn() }));
vi.mock('$lib/api/registrations', () => ({
	getRegistration: vi.fn(),
	listRegistrations: vi.fn(),
	submitPaymentAttempt: vi.fn(),
	submitRegistration: vi.fn()
}));
vi.mock('$lib/auth/session', () => ({ getAccessToken: vi.fn(), clearSession: vi.fn() }));
vi.mock('$lib/auth/navigation', () => ({ replaceInternalLocation: vi.fn() }));

const accessToken = 'access-token';
const user: CurrentUser = {
	id: 7,
	email: 'player@example.com',
	first_name: 'Player',
	last_name: 'One',
	school: 'HCMUS'
};
const game: PublicTournamentGame = {
	id: 10,
	game_name: 'Valorant',
	game_slug: 'valorant',
	team_size_min: 2,
	team_size_max: 2,
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
	starts_at: null,
	ends_at: null,
	location: 'HCMUS',
	tournament_games: [game]
};
const registration: RegistrationRead = {
	id: 33,
	tournament_game: {
		id: game.id,
		tournament_name: tournament.name,
		game_name: game.game_name,
		team_size_min: game.team_size_min,
		team_size_max: game.team_size_max,
		fee_amount: game.fee_amount,
		fee_currency: game.fee_currency
	},
	team_name: 'Blue Team',
	status: 'SUBMITTED',
	fee_amount_snapshot: '50000.00',
	fee_currency_snapshot: 'VND',
	submitted_at: '2026-07-19T00:00:00Z',
	payment_required: true,
	members: [
		{
			gamer_tag_snapshot: 'captain',
			school_snapshot: 'HCMUS',
			is_captain: true,
			display_order: 1
		},
		{
			gamer_tag_snapshot: 'teammate',
			school_snapshot: 'HCMUS',
			is_captain: false,
			display_order: 2
		}
	],
	status_events: [{ to_status: 'SUBMITTED', created_at: '2026-07-19T00:00:00Z' }],
	payment_attempts: []
};

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	mockPage.url = new URL('https://usec.test/tournaments/usec-summer-2026/games/10/register');
	mockPage.params = { id: '33' };
	vi.mocked(goto).mockReset().mockResolvedValue(undefined);
	vi.mocked(getAccessToken).mockReset().mockReturnValue(accessToken);
	vi.mocked(getCurrentUser).mockReset().mockResolvedValue(user);
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
});

describe('participant registration pages', () => {
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
		expect(container.querySelector('input[name="member-1-school"]')).toHaveValue('');
		expect(getCurrentUser).not.toHaveBeenCalled();
		await page.getByLabelText('Team name').fill('Blue Team');
		await page.getByLabelText('Gamer tag').nth(0).fill('captain');
		await page.getByLabelText('School').nth(0).fill('HCMUS');
		await page.getByLabelText('Gamer tag').nth(1).fill('teammate');
		await page.getByLabelText('School').nth(1).fill('HCMUS');
		await page.getByRole('button', { name: 'Submit registration' }).click();

		await vi.waitFor(() =>
			expect(submitRegistration).toHaveBeenCalledWith(accessToken, {
				tournament_game: 10,
				team_name: 'Blue Team',
				members: [
					{
						gamer_tag_snapshot: 'captain',
						school_snapshot: 'HCMUS',
						is_captain: true,
						display_order: 1
					},
					{
						gamer_tag_snapshot: 'teammate',
						school_snapshot: 'HCMUS',
						is_captain: false,
						display_order: 2
					}
				]
			})
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
		await page.getByLabelText('Gamer tag').nth(0).fill('captain');
		await page.getByLabelText('School').nth(0).fill('HCMUS');
		await page.getByLabelText('Gamer tag').nth(1).fill('teammate');
		await page.getByLabelText('School').nth(1).fill('HCMUS');
		await page.getByRole('button', { name: 'Submit registration' }).click();

		await expect.element(page.getByText('Roster invalid.')).toBeInTheDocument();
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
		await page.getByLabelText('Payment reference').fill('transfer-33');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(getRegistration).toHaveBeenCalledTimes(2));
		expect(submitPaymentAttempt).toHaveBeenCalledOnce();
		expect(appPage.params.id).toBe('33');
	});

	it('clears an expired session and redirects after payment submission', async () => {
		mockPage.url = new URL('https://usec.test/account/registrations/33');
		vi.mocked(submitPaymentAttempt).mockRejectedValue(
			new ApiRequestError(401, 'Authentication credentials were not provided.')
		);
		render(RegistrationDetailPage);

		await expect.element(page.getByLabelText('Payment reference')).toBeInTheDocument();
		await page.getByLabelText('Payment reference').fill('transfer-33');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(clearSession).toHaveBeenCalledOnce());
		expect(replaceInternalLocation).toHaveBeenCalledWith(
			'/en/auth/sign-in?redirect=%2Faccount%2Fregistrations%2F33'
		);
	});
});
