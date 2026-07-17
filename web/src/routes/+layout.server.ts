import {
	DISPLAY_TIME_ZONE_COOKIE,
	DISPLAY_TIME_ZONE_DEPENDENCY,
	resolveDisplayTimeZone
} from '$lib/time/tournament-time';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ cookies, depends }) => {
	depends(DISPLAY_TIME_ZONE_DEPENDENCY);

	return {
		displayTimeZone: resolveDisplayTimeZone(cookies.get(DISPLAY_TIME_ZONE_COOKIE))
	};
};
