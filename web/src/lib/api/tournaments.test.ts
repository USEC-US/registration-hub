import { describe, expect, it, vi } from 'vitest';
import { getTournament, listTournaments } from './tournaments';

describe('public tournament API wrappers', () => {
	it('forwards the supplied load fetch to the collection request', async () => {
		const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json([]));

		await listTournaments({ fetcher });

		expect(fetcher).toHaveBeenCalledWith(
			'http://localhost:8000/api/tournaments/',
			expect.objectContaining({ headers: expect.any(Headers) })
		);
	});

	it('encodes the slug and forwards the supplied load fetch to detail requests', async () => {
		const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
			Response.json({
				id: 1,
				name: 'Summer',
				slug: 'summer',
				description: '',
				starts_at: null,
				ends_at: null,
				location: '',
				tournament_games: []
			})
		);

		await getTournament('summer event', { fetcher });

		expect(fetcher).toHaveBeenCalledWith(
			'http://localhost:8000/api/tournaments/summer%20event/',
			expect.objectContaining({ headers: expect.any(Headers) })
		);
	});
});
