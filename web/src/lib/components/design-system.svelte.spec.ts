import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import type { PublicTournament, RegistrationRead } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import ErrorSummary from './forms/ErrorSummary.svelte';
import Field from './forms/Field.svelte';
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
