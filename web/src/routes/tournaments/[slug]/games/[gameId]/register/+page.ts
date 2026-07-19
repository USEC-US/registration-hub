import { error } from '@sveltejs/kit';
import { getTournament } from '$lib/api/tournaments';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => {
	const tournament = await getTournament(params.slug);
	const game = tournament.tournament_games.find((item) => item.id === Number(params.gameId));
	if (!game) error(404, 'Tournament game not found');
	return { tournament, game };
};
