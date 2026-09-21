import { parseDate } from '@internationalized/date';

export const NUMERIC_DATE_OPTIONS = {
	year: 'numeric',
	month: '2-digit',
	day: '2-digit'
} as const satisfies Intl.DateTimeFormatOptions;

export function dateLocale(locale: string): string {
	return { en: 'en-US', vi: 'vi-VN' }[locale] ?? locale;
}

function dateFormatter(locale: string): Intl.DateTimeFormat {
	return new Intl.DateTimeFormat(dateLocale(locale), {
		...NUMERIC_DATE_OPTIONS,
		calendar: 'gregory',
		numberingSystem: 'latn',
		timeZone: 'UTC'
	});
}

function dateParts(locale: string): Intl.DateTimeFormatPart[] {
	return dateFormatter(locale).formatToParts(new Date('2000-11-22T00:00:00Z'));
}

export function datePlaceholder(locale: string): string {
	return dateParts(locale)
		.map(({ type, value }) => {
			if (type === 'day') return 'dd';
			if (type === 'month') return 'mm';
			if (type === 'year') return 'yyyy';
			return value;
		})
		.join('');
}

export function formatDateOnly(isoDate: string, locale: string): string {
	// A birthday is a calendar date, so never convert it to the viewer's time zone.
	return dateFormatter(locale).format(parseDate(isoDate).toDate('UTC'));
}

export function parseDisplayDate(value: string, locale: string): string | undefined {
	const match = /^(\d{1,4})[./-](\d{1,4})[./-](\d{1,4})$/.exec(value.trim());
	if (!match) return undefined;
	const order = dateParts(locale).filter(({ type }) => ['year', 'month', 'day'].includes(type));
	const parts = Object.fromEntries(order.map(({ type }, index) => [type, match[index + 1]]));
	if (parts.year?.length !== 4) return undefined;
	try {
		return parseDate(
			`${parts.year}-${parts.month.padStart(2, '0')}-${parts.day.padStart(2, '0')}`
		).toString();
	} catch {
		return undefined;
	}
}
