import { expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { PublicTournament, RegistrationRead } from '$lib/api/types';
import StatusTimeline from './registrations/StatusTimeline.svelte';
import TournamentCard from './tournaments/TournamentCard.svelte';
import TournamentGameRow from './tournaments/TournamentGameRow.svelte';

const tournament: PublicTournament = {
	id: 17,
	name: 'Summer Tournament',
	slug: 'summer-tournament',
	description: 'Tournament description.',
	starts_at: '2026-08-15T01:00:00Z',
	ends_at: '2026-08-17T10:00:00Z',
	location: 'HCMUS',
	tournament_games: [
		{
			id: 31,
			game_name: 'Chess',
			game_slug: 'chess',
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

it('keeps tournament content while composing cards and registration-state badges', () => {
	const card = render(TournamentCard, { tournament, displayTimeZone: 'Asia/Ho_Chi_Minh' });
	const game = render(TournamentGameRow, {
		tournament,
		game: tournament.tournament_games[0],
		displayTimeZone: 'Asia/Ho_Chi_Minh'
	});

	expect(card.container.querySelector('[data-slot="card"]')).not.toBeNull();
	expect(game.container.querySelector('[data-slot="card"]')).not.toBeNull();
	expect(game.container.querySelector('[data-slot="badge"]')).not.toBeNull();
	expect(game.container.querySelector('a[href*="/tournaments/summer-tournament/games/31/register"]')).not.toBeNull();
});

it('keeps timeline list and time semantics while using badges for status labels', () => {
	const events: RegistrationRead['status_events'] = [
		{ to_status: 'SUBMITTED', created_at: '2026-07-21T01:00:00Z' },
		{ to_status: 'UNDER_REVIEW', created_at: '2026-07-22T02:30:00Z' }
	];
	const { container } = render(StatusTimeline, { props: { events } });

	expect(container.querySelector('ol')).not.toBeNull();
	expect(container.querySelectorAll('[data-slot="badge"]')).toHaveLength(2);
	expect(container.querySelectorAll('li')[1]).toHaveAttribute('aria-current', 'step');
	expect(container.querySelectorAll('time')[1]).toHaveAttribute('datetime', '2026-07-22T02:30:00Z');
});
