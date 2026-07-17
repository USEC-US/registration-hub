import { Temporal } from '@js-temporal/polyfill';

declare const displayTimeZoneBrand: unique symbol;

export type DisplayTimeZone = string & {
	readonly [displayTimeZoneBrand]: true;
};

export const DEFAULT_DISPLAY_TIME_ZONE = 'Asia/Ho_Chi_Minh' as DisplayTimeZone;
export const DISPLAY_TIME_ZONE_COOKIE = 'usec_display_time_zone';
export const DISPLAY_TIME_ZONE_DEPENDENCY = 'usec:display-time-zone';

const VALIDATION_INSTANT = Temporal.Instant.from('2000-01-01T00:00:00Z');

export function isValidDisplayTimeZone(value: unknown): value is DisplayTimeZone {
	if (typeof value !== 'string' || value.length === 0) return false;

	try {
		VALIDATION_INSTANT.toZonedDateTimeISO(value);
		return true;
	} catch {
		return false;
	}
}

export function resolveDisplayTimeZone(value: unknown): DisplayTimeZone {
	return isValidDisplayTimeZone(value) ? value : DEFAULT_DISPLAY_TIME_ZONE;
}

export function detectDisplayTimeZone(): DisplayTimeZone {
	return resolveDisplayTimeZone(Temporal.Now.timeZoneId());
}

export function createDisplayTimeZoneCookie(displayTimeZone: string): string {
	const value = encodeURIComponent(resolveDisplayTimeZone(displayTimeZone));
	return `${DISPLAY_TIME_ZONE_COOKIE}=${value}; Path=/; Max-Age=31536000; SameSite=Lax`;
}

function toZonedDateTime(utc: string, displayTimeZone: string): Temporal.ZonedDateTime {
	return Temporal.Instant.from(utc).toZonedDateTimeISO(resolveDisplayTimeZone(displayTimeZone));
}

export function formatTournamentDate(utc: string, locale: string, displayTimeZone: string): string {
	return toZonedDateTime(utc, displayTimeZone).toLocaleString(locale, {
		year: 'numeric',
		month: 'short',
		day: 'numeric'
	});
}

export function formatTournamentDateTime(
	utc: string,
	locale: string,
	displayTimeZone: string
): string {
	return toZonedDateTime(utc, displayTimeZone).toLocaleString(locale, {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit',
		timeZoneName: 'short'
	});
}
