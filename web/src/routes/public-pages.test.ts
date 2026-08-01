import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '$lib/api/client';
import { getTournament, listTournaments } from '$lib/api/tournaments';
import type { PublicTournament } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { load as homeLoad } from './+page';
import { load as tournamentListLoad } from './tournaments/+page';
import { load as tournamentDetailLoad } from './tournaments/[slug]/+page';
import { load as registrationLoad } from './tournaments/[slug]/games/[gameId]/register/+page';

vi.mock('$lib/api/tournaments', () => ({
	listTournaments: vi.fn(),
	getTournament: vi.fn()
}));

const tournament: PublicTournament = {
	id: 1,
	name: 'USEC Summer 2026',
	slug: 'usec-summer-2026',
	description: 'Summer tournament',
	cover_image: null,
	starts_at: null,
	ends_at: null,
	location: 'HCMUS',
	is_featured: false,
	tournament_games: [
		{
			id: 10,
			game_name: 'Valorant',
			game_slug: 'valorant',
			team_size_min: 5,
			team_size_max: 5,
			registration_opens_at: '2026-07-01T00:00:00Z',
			registration_closes_at: '2026-07-31T00:00:00Z',
			registration_capacity: 16,
			capacity_remaining: 16,
			fee_amount: '50000.00',
			fee_currency: 'VND',
			registration_state: 'open',
			is_registration_open: true
		}
	]
};

describe('public tournament loaders', () => {
	beforeEach(() => {
		overwriteGetLocale(() => 'en');
		vi.mocked(listTournaments).mockReset();
		vi.mocked(getTournament).mockReset();
	});

	it.each([
		['home', homeLoad],
		['tournament list', tournamentListLoad]
	])('loads published tournaments with the SvelteKit fetch for %s', async (_name, load) => {
		const fetcher = vi.fn<typeof fetch>();
		vi.mocked(listTournaments).mockResolvedValue([tournament]);

		const result = await load({ fetch: fetcher } as never);

		expect(result).toEqual({ tournaments: [tournament] });
		expect(listTournaments).toHaveBeenCalledWith({ fetcher });
	});

	it('loads a tournament detail with the SvelteKit fetch', async () => {
		const fetcher = vi.fn<typeof fetch>();
		vi.mocked(getTournament).mockResolvedValue(tournament);
		const result = await tournamentDetailLoad({
			fetch: fetcher,
			params: { slug: tournament.slug }
		} as never);

		expect(result).toEqual({ tournament });
		expect(getTournament).toHaveBeenCalledWith(tournament.slug, { fetcher });
	});

	it('loads a registration game with the SvelteKit fetch', async () => {
		const fetcher = vi.fn<typeof fetch>();
		vi.mocked(getTournament).mockResolvedValue(tournament);

		const result = await registrationLoad({
			fetch: fetcher,
			params: { slug: tournament.slug, gameId: '10' }
		} as never);

		expect(result).toEqual({ tournament, game: tournament.tournament_games[0] });
		expect(getTournament).toHaveBeenCalledWith(tournament.slug, { fetcher });
	});

	it('localizes a missing registration game error', async () => {
		overwriteGetLocale(() => 'vi');
		vi.mocked(getTournament).mockResolvedValue(tournament);

		await expect(
			registrationLoad({
				fetch: vi.fn(),
				params: { slug: tournament.slug, gameId: '999' }
			} as never)
		).rejects.toMatchObject({
			status: 404,
			body: { message: 'Không tìm thấy nội dung thi đấu' }
		});
	});

	it('maps only API not-found responses to a route 404', async () => {
		vi.mocked(getTournament).mockRejectedValue(new ApiRequestError(404, 'Not found.'));

		await expect(
			tournamentDetailLoad({ fetch: vi.fn(), params: { slug: 'missing' } } as never)
		).rejects.toMatchObject({
			status: 404,
			body: { message: 'Tournament not found' }
		});
	});

	it('preserves unexpected API failures', async () => {
		const cause = new ApiRequestError(503, 'Unavailable.');
		vi.mocked(getTournament).mockRejectedValue(cause);

		await expect(
			tournamentDetailLoad({ fetch: vi.fn(), params: { slug: tournament.slug } } as never)
		).rejects.toBe(cause);
	});
});
