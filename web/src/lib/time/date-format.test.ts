import { describe, expect, it } from 'vitest';
import { datePlaceholder, formatDateOnly, parseDisplayDate } from './date-format';

describe('localized calendar dates', () => {
	it.each([
		['vi', '12/03/2005', 'dd/mm/yyyy'],
		['en', '03/12/2005', 'mm/dd/yyyy'],
		['de-DE', '12.03.2005', 'dd.mm.yyyy']
	])('formats and parses %s without shifting the day', (locale, displayed, placeholder) => {
		expect(formatDateOnly('2005-03-12', locale)).toBe(displayed);
		expect(parseDisplayDate(displayed, locale)).toBe('2005-03-12');
		expect(datePlaceholder(locale)).toBe(placeholder);
	});
	it('uses locale ordering for ambiguous input and accepts a leap day', () => {
		expect(parseDisplayDate('03/04/2005', 'vi')).toBe('2005-04-03');
		expect(parseDisplayDate('03/04/2005', 'en')).toBe('2005-03-04');
		expect(parseDisplayDate('29/02/2024', 'vi')).toBe('2024-02-29');
	});
	it.each(['31/02/2024', '29/02/2023', '12/13/2005', '0/3/2005', '12/3/05', '12/3', ''])(
		'rejects invalid or incomplete dates: %s',
		(value) => {
			expect(parseDisplayDate(value, 'vi')).toBeUndefined();
		}
	);
});
