import { afterEach, describe, expect, it } from 'vitest';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { sanitizeInternalRedirect } from './navigation';

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('sanitizeInternalRedirect', () => {
	it.each([
		'/account/profile?section=identity#school',
		'/vi/account/registrations?status=SUBMITTED#latest'
	])('keeps a localized internal destination: %s', (destination) => {
		expect(sanitizeInternalRedirect(destination)).toBe(destination);
	});

	it.each([
		'https://attacker.example/account/profile',
		'//attacker.example/account/profile',
		'javascript:alert(1)',
		'/safe\\attacker.example',
		'/safe%5Cattacker.example',
		'/safe\nnext',
		'/safe%0Anext',
		'/malformed%2'
	])('rejects an unsafe or malformed destination: %s', (destination) => {
		expect(sanitizeInternalRedirect(destination)).toBe('/account/registrations');
	});

	it('uses a locale-aware registrations fallback', () => {
		overwriteGetLocale(() => 'vi');

		expect(sanitizeInternalRedirect(null)).toBe('/vi/account/registrations');
	});
});
