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
import RegistrationsPage from './account/registrations/+page.svelte';
import RegistrationDetailPage from './account/registrations/[id]/+page.svelte';

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
	payment_due_at: null,
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

describe('account registration pages', () => {
	it('lists registration snapshots with links to their details', async () => {
		mockPage.url = new URL('https://usec.test/account/registrations');
		const { container } = render(RegistrationsPage);

		await expect.element(page.getByText(tournament.name)).toBeInTheDocument();
		await expect.element(page.getByText(game.game_name)).toBeInTheDocument();
		await expect.element(page.getByText('Submitted', { exact: true }).first()).toBeInTheDocument();
		expect(container.querySelector('[data-slot="card"]')).not.toBeNull();
		expect(container.querySelector('[data-slot="badge"]')).not.toBeNull();
		expect(container.querySelector('a[href="/en/account/registrations/33"]')).not.toBeNull();
		expect(container.textContent).toContain('Payment not received');
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
		await expect
			.element(page.getByLabelText('Transfer content'))
			.toHaveProperty('tagName', 'OUTPUT');
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

		await expect.element(page.getByLabelText('Transfer content')).toBeInTheDocument();
		const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!;
		const transfer = new DataTransfer();
		transfer.items.add(new File(['proof'], 'proof.png', { type: 'image/png' }));
		fileInput.files = transfer.files;
		fileInput.dispatchEvent(new Event('change', { bubbles: true }));
		await expect
			.element(page.getByLabelText('Transfer content'))
			.toHaveProperty('tagName', 'OUTPUT');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(clearSession).toHaveBeenCalledOnce());
		expect(replaceInternalLocation).toHaveBeenCalledWith(
			'/en/auth/sign-in?redirect=%2Faccount%2Fregistrations%2F33'
		);
	});
});
