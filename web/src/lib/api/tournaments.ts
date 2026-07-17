import { requestJson } from './client';
import type { PublicTournament } from './types';

export function listTournaments() {
	return requestJson<PublicTournament[]>('/tournaments/');
}

export function getTournament(slug: string) {
	return requestJson<PublicTournament>(`/tournaments/${slug}/`);
}
