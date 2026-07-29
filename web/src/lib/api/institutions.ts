import { requestJson } from './client';
import type { Institution } from './types';

export function searchInstitutions(query: string): Promise<Institution[]> {
	return requestJson<Institution[]>(`/institutions/?q=${encodeURIComponent(query)}`);
}
