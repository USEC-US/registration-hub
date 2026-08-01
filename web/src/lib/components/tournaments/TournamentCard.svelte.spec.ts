import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import type { PublicTournament } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { resolveDisplayTimeZone } from '$lib/time/tournament-time';
import TournamentCard from './TournamentCard.svelte';

const displayTimeZone = resolveDisplayTimeZone('Asia/Ho_Chi_Minh');

const tournament: PublicTournament = {
	id: 1,
	name: 'USEC Summer 2026',
	slug: 'usec-summer-2026',
	description: 'A university tournament for HCMUS students.',
	cover_image: null,
	starts_at: '2026-08-15T01:00:00Z',
	ends_at: '2026-08-17T10:00:00Z',
	location: 'HCMUS',
	is_featured: false,
	tournament_games: [
		{
			id: 9,
			game_name: 'Valorant',
			game_slug: 'valorant',
			team_size_min: 5,
			team_size_max: 5,
			registration_opens_at: '2026-07-20T01:00:00Z',
			registration_closes_at: '2026-08-10T10:00:00Z',
			registration_capacity: 32,
			capacity_remaining: 12,
			fee_amount: '50000.00',
			fee_currency: 'VND',
			registration_state: 'open',
			is_registration_open: true
		}
	]
};

beforeEach(() => {
	overwriteGetLocale(() => 'en');
});

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('TournamentCard', () => {
	it('uses a single whole-card link target for the grid card', async () => {
		const { container } = render(TournamentCard, {
			tournament,
			displayTimeZone,
			variant: 'grid'
		});

		const article = container.querySelector('article');
		const links = article?.querySelectorAll('a');

		expect(links).toHaveLength(1);
		expect(article?.firstElementChild?.tagName).toBe('A');
		await expect
			.element(page.getByRole('link', { name: tournament.name }))
			.toHaveAttribute('href', '/en/tournaments/usec-summer-2026');
	});

	it('lets the grid card date range occupy the full bottom row', () => {
		const { container } = render(TournamentCard, {
			tournament,
			displayTimeZone,
			variant: 'grid'
		});
		const metadataCells = [...container.querySelectorAll('dl > div')];
		const datesCell = metadataCells.find((cell) => cell.querySelector('dt')?.textContent === 'Dates');

		expect(datesCell).toHaveClass('col-span-2');
		expect(metadataCells.at(-1)).toBe(datesCell);
	});
});
