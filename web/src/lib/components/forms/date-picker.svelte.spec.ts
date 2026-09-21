import { fromStore, writable } from 'svelte/store';
import { expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import DatePicker from './DatePicker.svelte';

it.each([
	['vi', '12/03/2005', 'Mở lịch chọn ngày', 'Chọn tháng', 'Chọn năm'],
	['en', '03/12/2005', 'Open date picker', 'Choose month', 'Choose year']
] as const)(
	'supports localized typing and calendar selection in %s',
	async (locale, displayed, openLabel, monthLabel, yearLabel) => {
		overwriteGetLocale(() => locale);
		const state = fromStore(writable('2005-03-12'));
		const { container } = render(DatePicker, {
			id: 'birthday',
			name: 'birthday',
			locale,
			required: true,
			max: '2026-09-12',
			get value() {
				return state.current;
			},
			set value(value) {
				state.current = value;
			}
		});
		await expect.element(page.getByRole('textbox')).toHaveValue(displayed);
		await expect.element(page.getByRole('textbox')).toBeRequired();
		await page.getByRole('textbox').fill(locale === 'vi' ? '29/02/2004' : '02/29/2004');
		expect(state.current).toBe('2004-02-29');
		expect(container.querySelector<HTMLInputElement>('input[type=hidden]')!.value).toBe(
			'2004-02-29'
		);
		await page.getByRole('button', { name: openLabel }).click();
		await expect.element(page.getByRole('combobox', { name: monthLabel })).toBeVisible();
		await expect.element(page.getByRole('combobox', { name: yearLabel })).toBeVisible();
		// Day labels and headers must retain enough text to distinguish Vietnamese weekdays.
		const headers = [...document.querySelectorAll('[data-calendar-head-cell]')].map(
			(el) => el.textContent
		);
		expect(new Set(headers).size).toBe(7);
		await page
			.getByRole('button')
			.filter({ hasText: /^28$/ })
			.all()
			.find((day) => day.element().getAttribute('data-value') === '2004-02-28')!
			.click();
		expect(state.current).toBe('2004-02-28');
		await expect
			.element(page.getByRole('textbox'))
			.toHaveValue(locale === 'vi' ? '28/02/2004' : '02/28/2004');
	}
);

it('clears stale ISO values and blocks invalid or future dates without discarding typed text', async () => {
	overwriteGetLocale(() => 'en');
	const state = fromStore(writable('2005-03-12'));
	render(DatePicker, {
		id: 'birthday',
		name: 'birthday',
		locale: 'en',
		required: true,
		max: '2026-09-12',
		get value() {
			return state.current;
		},
		set value(value) {
			state.current = value;
		}
	});
	for (const text of ['02/31/2005', '09/13/2026', '03/']) {
		await page.getByRole('textbox').fill(text);
		await expect.element(page.getByRole('textbox')).toHaveValue(text);
		await expect.element(page.getByRole('textbox')).toBeInvalid();
		expect(state.current).toBe('');
	}
	await page.getByRole('textbox').fill('09/12/2026');
	await expect.element(page.getByRole('textbox')).toBeValid();
	expect(state.current).toBe('2026-09-12');
});

it('reformats an existing birth date when the site language changes', async () => {
	const language = fromStore(writable('en'));
	const birthday = fromStore(writable('2005-03-12'));
	render(DatePicker, {
		id: 'birthday',
		name: 'birthday',
		get locale() {
			return language.current;
		},
		get value() {
			return birthday.current;
		},
		set value(value) {
			birthday.current = value;
		}
	});
	await expect.element(page.getByRole('textbox')).toHaveValue('03/12/2005');
	language.current = 'vi';
	await expect.element(page.getByRole('textbox')).toHaveValue('12/03/2005');
	expect(birthday.current).toBe('2005-03-12');
});
