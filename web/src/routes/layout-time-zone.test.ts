import { describe, expect, it, vi } from 'vitest';
import {
	DEFAULT_DISPLAY_TIME_ZONE,
	DISPLAY_TIME_ZONE_COOKIE,
	DISPLAY_TIME_ZONE_DEPENDENCY
} from '$lib/time/tournament-time';
import { load } from './+layout.server';

async function runLayout(cookieValue?: string) {
	const depends = vi.fn();
	const get = vi.fn((name: string) =>
		name === DISPLAY_TIME_ZONE_COOKIE ? cookieValue : undefined
	);

	const result = await load({ cookies: { get }, depends } as never);
	return { depends, get, result };
}

describe('display timezone layout cookie', () => {
	it('returns a valid viewer display zone and registers only its custom dependency', async () => {
		const { depends, get, result } = await runLayout('America/New_York');

		expect(result).toEqual({ displayTimeZone: 'America/New_York' });
		expect(get).toHaveBeenCalledWith(DISPLAY_TIME_ZONE_COOKIE);
		expect(depends).toHaveBeenCalledOnce();
		expect(depends).toHaveBeenCalledWith(DISPLAY_TIME_ZONE_DEPENDENCY);
	});

	it.each([undefined, 'Mars/Olympus'])(
		'falls back for an absent or invalid cookie: %s',
		async (cookie) => {
			const { result } = await runLayout(cookie);

			expect(result).toEqual({ displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE });
		}
	);
});
