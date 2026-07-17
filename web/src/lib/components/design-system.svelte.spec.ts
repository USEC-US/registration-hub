import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { createRawSnippet } from 'svelte';
import type { PublicTournament, RegistrationRead } from '$lib/api/types';
import { localizeCurrentHref } from '$lib/navigation';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import ErrorSummary from './forms/ErrorSummary.svelte';
import Field from './forms/Field.svelte';
import AppShell from './layout/AppShell.svelte';
import StatusTimeline from './registrations/StatusTimeline.svelte';
import TournamentCard from './tournaments/TournamentCard.svelte';
import TournamentGameRow from './tournaments/TournamentGameRow.svelte';

const tournament: PublicTournament = {
	id: 17,
	name: 'Giải Mùa Hè',
	slug: 'giai-mua-he',
	description: 'Giải đấu dành cho sinh viên HCMUS.',
	starts_at: '2026-08-15T01:00:00Z',
	ends_at: '2026-08-17T10:00:00Z',
	location: 'HCMUS',
	tournament_games: [
		{
			id: 31,
			game_name: 'Cờ vua',
			game_slug: 'co-vua',
			team_size_min: 1,
			team_size_max: 1,
			registration_opens_at: '2026-07-20T01:00:00Z',
			registration_closes_at: '2026-08-10T10:00:00Z',
			registration_capacity: 64,
			capacity_remaining: 12,
			fee_amount: '50000.00',
			fee_currency: 'VND',
			registration_state: 'open',
			is_registration_open: true
		}
	]
};

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('form components', () => {
	it('associates the field label and error with its input', async () => {
		render(Field, {
			label: 'Email',
			name: 'email',
			value: '',
			error: 'Enter an email address.',
			type: 'email'
		});

		const input = page.getByRole('textbox', { name: 'Email' });

		await expect.element(input).toHaveAttribute('aria-describedby', 'email-error');
		await expect.element(input).toHaveAttribute('aria-invalid', 'true');
		await expect
			.element(page.getByText('Enter an email address.'))
			.toHaveAttribute('id', 'email-error');
	});

	it('forwards browser input attributes', async () => {
		const fieldProps = {
			label: 'Email',
			name: 'email',
			value: '',
			type: 'email' as const,
			autocomplete: 'email' as const,
			spellcheck: false
		};
		render(Field, fieldProps);

		const input = page.getByRole('textbox', { name: 'Email' });
		await expect.element(input).toHaveAttribute('autocomplete', 'email');
		await expect.element(input).toHaveAttribute('spellcheck', 'false');
	});

	it('renders no error summary container when there are no errors', () => {
		const { container } = render(ErrorSummary, { errors: [] });

		expect(container.childElementCount).toBe(0);
	});
});

describe('tournament components', () => {
	it('localizes tournament chrome and registration state without translating source content', async () => {
		overwriteGetLocale(() => 'vi');
		render(TournamentCard, { tournament });
		render(TournamentGameRow, { tournament, game: tournament.tournament_games[0] });

		await expect.element(page.getByText('Giải Mùa Hè')).toBeInTheDocument();
		await expect.element(page.getByText('Cờ vua')).toBeInTheDocument();
		await expect.element(page.getByText('Địa điểm')).toBeInTheDocument();
		await expect.element(page.getByText('Đang mở', { exact: true })).toBeInTheDocument();
	});

	it('uses the numeric game id and current locale in the registration route', async () => {
		overwriteGetLocale(() => 'vi');
		render(TournamentGameRow, { tournament, game: tournament.tournament_games[0] });

		await expect
			.element(page.getByRole('link', { name: 'Đăng ký' }))
			.toHaveAttribute('href', '/vi/tournaments/giai-mua-he/games/31/register');
	});

	it('preserves the current locale in shell and tournament navigation', () => {
		overwriteGetLocale(() => 'vi');
		const children = createRawSnippet(() => ({ render: () => '<p>Content</p>' }));
		const shell = render(AppShell, { children });
		const card = render(TournamentCard, { tournament });

		expect(shell.container.querySelector('a[href="/vi/"]')).not.toBeNull();
		expect(shell.container.querySelector('a[href="/vi/tournaments"]')).not.toBeNull();
		expect(shell.container.querySelector('a[href="/vi/account/registrations"]')).not.toBeNull();
		expect(shell.container.querySelector('a[href="/vi/account/profile"]')).not.toBeNull();
		expect(shell.container.querySelector('a[href="/vi/auth/sign-in"]')).not.toBeNull();
		expect(card.container.querySelectorAll('a[href="/vi/tournaments/giai-mua-he"]')).toHaveLength(
			2
		);
	});

	it('preserves the query and hash when switching locale', () => {
		const currentUrl = {
			pathname: '/tournaments',
			search: '?registration=open',
			hash: '#games'
		};

		expect(localizeCurrentHref(currentUrl, 'vi')).toBe('/vi/tournaments?registration=open#games');
	});
});

describe('StatusTimeline', () => {
	it('uses ordered-list, current-step, and machine-readable time semantics', async () => {
		const events: RegistrationRead['status_events'] = [
			{ to_status: 'SUBMITTED', created_at: '2026-07-21T01:00:00Z' },
			{ to_status: 'UNDER_REVIEW', created_at: '2026-07-22T02:30:00Z' }
		];
		const { container } = render(StatusTimeline, { props: { events } });

		await expect
			.element(page.getByRole('list', { name: 'Registration status timeline' }))
			.toBeInTheDocument();
		expect(container.querySelectorAll('li')).toHaveLength(2);
		expect(container.querySelectorAll('li')[1]).toHaveAttribute('aria-current', 'step');
		expect(container.querySelectorAll('time')[0]).toHaveAttribute(
			'datetime',
			'2026-07-21T01:00:00Z'
		);
		expect(container.querySelectorAll('time')[1]).toHaveAttribute(
			'datetime',
			'2026-07-22T02:30:00Z'
		);
		await expect.element(page.getByText('Submitted')).toBeInTheDocument();
		await expect.element(page.getByText('Under review')).toBeInTheDocument();
	});
});
