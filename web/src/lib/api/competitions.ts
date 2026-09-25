import { requestJson } from './client';
import type { ApiRequestOptions } from './client';
import type { PublicCompetition, PublicCompetitionChangesPage } from './types';

type CompetitionRequestOptions = Pick<ApiRequestOptions, 'fetcher'>;

export class CompetitionRevisionMismatchError extends Error {
	constructor() {
		super('Competition changed while the bracket was loading.');
		this.name = 'CompetitionRevisionMismatchError';
	}
}

export function getCompetition(divisionId: number, options: CompetitionRequestOptions = {}) {
	return requestJson<PublicCompetition>(`/tournament-games/${divisionId}/competition/`, options);
}

export function getCompetitionChanges(
	divisionId: number,
	options: CompetitionRequestOptions & { cursor?: string } = {}
) {
	const { cursor, ...requestOptions } = options;
	const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
	return requestJson<PublicCompetitionChangesPage>(
		`/tournament-games/${divisionId}/competition/changes/${query}`,
		requestOptions
	);
}

export async function getCompetitionSnapshot(
	divisionId: number,
	options: CompetitionRequestOptions = {}
) {
	for (let attempt = 0; attempt < 2; attempt++) {
		const [competition, changes] = await Promise.all([
			getCompetition(divisionId, options),
			getCompetitionChanges(divisionId, options)
		]);
		if (competition.competition_revision === changes.competition_revision) {
			return { competition, changes };
		}
	}
	throw new CompetitionRevisionMismatchError();
}
