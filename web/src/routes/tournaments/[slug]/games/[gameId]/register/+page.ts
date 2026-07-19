import { error } from '@sveltejs/kit';
import { getTournament } from '$lib/api/tournaments';
import * as m from '$lib/paraglide/messages';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const tournament = await getTournament(params.slug, { fetcher: fetch });
	const game = tournament.tournament_games.find((item) => item.id === Number(params.gameId));
	if (!game) error(404, m.tournament_game_not_found());
	return { tournament, game };
};
