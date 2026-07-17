import { listTournaments } from '$lib/api/tournaments';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	tournaments: await listTournaments({ fetcher: fetch })
});
