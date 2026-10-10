import { describe, expect, it, vi } from 'vitest';
import {
	CompetitionRevisionMismatchError,
	getCompetitionChanges,
	getCompetitionSnapshot
} from './competitions';

const competition = {
	id: 1,
	competition_revision: 4,
	tournament_game_id: 9,
	tournament_slug: 'summer',
	tournament_name: 'Summer',
	game_name: 'Valorant',
	stages: [
		{
			format: 'DOUBLE_ELIMINATION',
			grand_final_policy: 'RESET',
			groups: [],
			round_robin_rules: null,
			swiss_rules: null,
			swiss_standings: [],
			rounds: [
				{
					section: 'LOWER',
					group_id: null,
					tie_resolution_id: null,
					effective_series_mode: 'BEST_OF',
					resting_entry: null,
					matches: [
						{
							status: 'CONDITIONAL',
							slots: [{ source_match_id: 31, source_outcome: 'LOSER' }]
						}
					]
				}
			]
		}
	]
};

const changes = {
	next: null,
	previous: null,
	results: [],
	competition_revision: 4
};

describe('public competition API wrappers', () => {
	it('forwards an encoded changes cursor', async () => {
		const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(changes));

		await getCompetitionChanges(9, { fetcher, cursor: 'next page==' });

		expect(fetcher).toHaveBeenCalledWith(
			'http://localhost:8000/api/tournament-games/9/competition/changes/?cursor=next%20page%3D%3D',
			expect.objectContaining({ headers: expect.any(Headers) })
		);
	});

	it('retries both reads after a revision mismatch', async () => {
		const responses = [competition, { ...changes, competition_revision: 3 }, competition, changes];
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementation(async () => Response.json(responses.shift()));

		await expect(getCompetitionSnapshot(9, { fetcher })).resolves.toEqual({
			competition,
			changes
		});
		expect(fetcher).toHaveBeenCalledTimes(4);
	});

	it('preserves double-elimination routing fields in a consistent snapshot', async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementation(async (url) =>
				Response.json(String(url).endsWith('/changes/') ? changes : competition)
			);

		const snapshot = await getCompetitionSnapshot(9, { fetcher });

		expect(snapshot.competition.stages[0]).toMatchObject({
			format: 'DOUBLE_ELIMINATION',
			grand_final_policy: 'RESET',
			groups: [],
			round_robin_rules: null,
			swiss_rules: null,
			swiss_standings: [],
			rounds: [
				{
					section: 'LOWER',
					group_id: null,
					tie_resolution_id: null,
					effective_series_mode: 'BEST_OF',
					resting_entry: null,
					matches: [
						{
							status: 'CONDITIONAL',
							slots: [{ source_match_id: 31, source_outcome: 'LOSER' }]
						}
					]
				}
			]
		});
	});

	it('rejects two inconsistent snapshots', async () => {
		const fetcher = vi
			.fn<typeof fetch>()
			.mockImplementation(async (url) =>
				Response.json(
					String(url).endsWith('/changes/') ? { ...changes, competition_revision: 3 } : competition
				)
			);

		await expect(getCompetitionSnapshot(9, { fetcher })).rejects.toBeInstanceOf(
			CompetitionRevisionMismatchError
		);
		expect(fetcher).toHaveBeenCalledTimes(4);
	});
});
