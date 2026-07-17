import { afterEach, describe, expect, it, vi } from 'vitest';
import { invalidate } from '$app/navigation';
import { Temporal } from '@js-temporal/polyfill';
import { render } from 'vitest-browser-svelte';
import { createRawSnippet } from 'svelte';
import {
	DEFAULT_DISPLAY_TIME_ZONE,
	DISPLAY_TIME_ZONE_COOKIE,
	DISPLAY_TIME_ZONE_DEPENDENCY
} from '$lib/time/tournament-time';
import RootLayout from './+layout.svelte';

vi.mock('$app/navigation', () => ({ invalidate: vi.fn() }));

const children = createRawSnippet(() => ({ render: () => '<p>Layout content</p>' }));

afterEach(() => {
	document.cookie = `${DISPLAY_TIME_ZONE_COOKIE}=; Path=/; Max-Age=0`;
	vi.restoreAllMocks();
	vi.mocked(invalidate).mockReset();
});

describe('display timezone hydration sync', () => {
	it('stores a different detected viewer zone and invalidates only the layout dependency', async () => {
		vi.spyOn(Temporal.Now, 'timeZoneId').mockReturnValue('America/New_York');

		render(RootLayout, {
			children,
			data: { displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE }
		} as never);

		await vi.waitFor(() => {
			expect(document.cookie).toContain(`${DISPLAY_TIME_ZONE_COOKIE}=America%2FNew_York`);
			expect(invalidate).toHaveBeenCalledOnce();
			expect(invalidate).toHaveBeenCalledWith(DISPLAY_TIME_ZONE_DEPENDENCY);
		});
	});

	it('does not write or invalidate when server and viewer zones already match', async () => {
		vi.spyOn(Temporal.Now, 'timeZoneId').mockReturnValue(DEFAULT_DISPLAY_TIME_ZONE);

		render(RootLayout, {
			children,
			data: { displayTimeZone: DEFAULT_DISPLAY_TIME_ZONE }
		} as never);

		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(document.cookie).not.toContain(`${DISPLAY_TIME_ZONE_COOKIE}=`);
		expect(invalidate).not.toHaveBeenCalled();
	});
});
