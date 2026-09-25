import { ApiRequestError } from '$lib/api/client';
import { CompetitionRevisionMismatchError, getCompetitionSnapshot } from '$lib/api/competitions';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const gameId = Number(params.gameId);
	const unavailable = { state: 'unavailable' as const, slug: params.slug, gameId };
	if (!Number.isInteger(gameId)) return unavailable;

	try {
		const snapshot = await getCompetitionSnapshot(gameId, { fetcher: fetch });
		if (
			snapshot.competition.tournament_slug !== params.slug ||
			snapshot.competition.tournament_game_id !== gameId
		) {
			return unavailable;
		}
		return { state: 'ready' as const, slug: params.slug, gameId, ...snapshot };
	} catch (cause) {
		if (cause instanceof ApiRequestError && cause.status === 404) return unavailable;
		if (cause instanceof CompetitionRevisionMismatchError) {
			return { state: 'refresh' as const, slug: params.slug, gameId };
		}
		throw cause;
	}
};
