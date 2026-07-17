import { error } from '@sveltejs/kit';
import { ApiRequestError } from '$lib/api/client';
import { getTournament } from '$lib/api/tournaments';
import * as m from '$lib/paraglide/messages';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	try {
		return {
			tournament: await getTournament(params.slug, { fetcher: fetch })
		};
	} catch (cause) {
		if (cause instanceof ApiRequestError && cause.status === 404) {
			error(404, m.tournament_not_found());
		}
		throw cause;
	}
};
