import { describe, expect, it, vi } from 'vitest';
import { load } from './tournaments/[slug]/games/[gameId]/bracket/+page';

const snapshot = {
	competition: {
		id: 1,
		competition_revision: 4,
		tournament_game_id: 9,
		tournament_slug: 'summer',
		tournament_name: 'Summer',
		game_name: 'Valorant',
		stages: [
			{
				format: 'DOUBLE_ELIMINATION',
				grand_final_policy: 'NO_RESET',
				rounds: [
					{
						section: 'FINALS',
						matches: [
							{
								status: 'NOT_REQUIRED',
								slots: [{ source_match_id: 42, source_outcome: 'WINNER' }]
							}
						]
					}
				]
			}
		]
	},
	changes: {
		next: null,
		previous: null,
		results: [],
		competition_revision: 4
	}
};

describe('public bracket loader', () => {
	it('loads a consistent published bracket with the SvelteKit fetch', async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementation(async (url) =>
				Response.json(String(url).endsWith('/changes/') ? snapshot.changes : snapshot.competition)
			);

		await expect(
			load({ fetch: fetcher, params: { slug: 'summer', gameId: '9' } } as never)
		).resolves.toEqual({ state: 'ready', slug: 'summer', gameId: 9, ...snapshot });
		expect(fetcher).toHaveBeenCalledTimes(2);
	});

	it('keeps double-elimination fields in ready page data', async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementation(async (url) =>
				Response.json(String(url).endsWith('/changes/') ? snapshot.changes : snapshot.competition)
			);

		const result = await load({
			fetch: fetcher,
			params: { slug: 'summer', gameId: '9' }
		} as never);

		expect(result).toMatchObject({
			state: 'ready',
			competition: {
				stages: [
					{
						grand_final_policy: 'NO_RESET',
						rounds: [
							{
								section: 'FINALS',
								matches: [
									{
										status: 'NOT_REQUIRED',
										slots: [{ source_match_id: 42, source_outcome: 'WINNER' }]
									}
								]
							}
						]
					}
				]
			}
		});
	});

	it.each([
		['missing bracket', '9'],
		['invalid game id', 'invalid']
	])('uses the unavailable state for %s', async (_name, gameId) => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockResolvedValue(Response.json({ detail: 'Not found.' }, { status: 404 }));

		await expect(
			load({ fetch: fetcher, params: { slug: 'summer', gameId } } as never)
		).resolves.toMatchObject({ state: 'unavailable', slug: 'summer' });
	});

	it('does not expose a bracket through the wrong tournament slug', async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementation(async (url) =>
				Response.json(String(url).endsWith('/changes/') ? snapshot.changes : snapshot.competition)
			);

		await expect(
			load({ fetch: fetcher, params: { slug: 'other', gameId: '9' } } as never)
		).resolves.toEqual({ state: 'unavailable', slug: 'other', gameId: 9 });
	});

	it('shows an explicit refresh state after repeated revision mismatches', async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementation(async (url) =>
				Response.json(
					String(url).endsWith('/changes/')
						? { ...snapshot.changes, competition_revision: 3 }
						: snapshot.competition
				)
			);

		await expect(
			load({ fetch: fetcher, params: { slug: 'summer', gameId: '9' } } as never)
		).resolves.toEqual({ state: 'refresh', slug: 'summer', gameId: 9 });
		expect(fetcher).toHaveBeenCalledTimes(4);
	});
});
