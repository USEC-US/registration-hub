import { requestJson } from './client';
import type { ApiRequestOptions } from './client';
import type { PublicTournament } from './types';

type PublicTournamentRequestOptions = Pick<ApiRequestOptions, 'fetcher'>;

export function listTournaments(options: PublicTournamentRequestOptions = {}) {
	return requestJson<PublicTournament[]>('/tournaments/', options);
}

export function getTournament(slug: string, options: PublicTournamentRequestOptions = {}) {
	return requestJson<PublicTournament>(`/tournaments/${encodeURIComponent(slug)}/`, options);
}
