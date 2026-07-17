import { describe, expect, it } from 'vitest';
import {
	DEFAULT_DISPLAY_TIME_ZONE,
	createDisplayTimeZoneCookie,
	formatTournamentDate,
	formatTournamentDateTime,
	isValidDisplayTimeZone,
	resolveDisplayTimeZone
} from './tournament-time';

describe('tournament display time', () => {
	it('validates arbitrary IANA zones through Temporal and falls back safely', () => {
		expect(isValidDisplayTimeZone('America/New_York')).toBe(true);
		expect(isValidDisplayTimeZone('Mars/Olympus')).toBe(false);
		expect(resolveDisplayTimeZone('America/New_York')).toBe('America/New_York');
		expect(resolveDisplayTimeZone('Mars/Olympus')).toBe(DEFAULT_DISPLAY_TIME_ZONE);
		expect(resolveDisplayTimeZone(undefined)).toBe(DEFAULT_DISPLAY_TIME_ZONE);
	});

	it('converts a UTC boundary into the explicit display zone without changing the source value', () => {
		const utc = '2026-08-14T18:30:00Z';

		expect(formatTournamentDate(utc, 'en', 'Asia/Ho_Chi_Minh')).toBe('Aug 15, 2026');
		expect(formatTournamentDateTime(utc, 'en', 'Asia/Ho_Chi_Minh')).toBe(
			'Aug 15, 2026, 1:30 AM GMT+7'
		);
		expect(utc).toBe('2026-08-14T18:30:00Z');
	});

	it('serializes a non-sensitive viewer zone cookie with a narrow lifetime and path', () => {
		expect(createDisplayTimeZoneCookie('America/New_York')).toBe(
			'usec_display_time_zone=America%2FNew_York; Path=/; Max-Age=31536000; SameSite=Lax'
		);
	});
});
