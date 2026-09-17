import { describe, expect, it } from 'vitest';
import { isStagingHost } from './staging';

describe('isStagingHost', () => {
	it.each([
		'staging.usec.vn',
		'registration-staging.org',
		'staging-hub.hcmus.edu.vn',
		'staging',
		'subdomain.staging.example.com'
	])('detects staging when hostname includes "staging": %s', (hostname) => {
		const url = new URL(`https://${hostname}/tournaments`);
		expect(isStagingHost(url, false)).toBe(true);
		expect(isStagingHost(url, true)).toBe(true);
	});

	it.each(['registration.usec.vn', 'tournament.hcmus.edu.vn', 'localhost', '127.0.0.1', 'usec.vn'])(
		'does not detect staging on normal hostname without staging flag: %s',
		(hostname) => {
			const url = new URL(`https://${hostname}/tournaments`);
			expect(isStagingHost(url, false)).toBe(false);
		}
	);

	it('enables staging when "?staging" query param is present in dev mode', () => {
		const url = new URL('http://localhost:5173/?staging');
		expect(isStagingHost(url, true)).toBe(true);
	});

	it('enables staging when "?staging=1" query param is present in dev mode', () => {
		const url = new URL('http://localhost:5173/tournaments?staging=1');
		expect(isStagingHost(url, true)).toBe(true);
	});

	it('does not enable staging with "?staging" query param in non-dev mode', () => {
		const url = new URL('https://registration.usec.vn/?staging');
		expect(isStagingHost(url, false)).toBe(false);
	});

	it('handles missing searchParams gracefully', () => {
		expect(isStagingHost({ hostname: 'staging.usec.vn' })).toBe(true);
		expect(isStagingHost({ hostname: 'usec.vn' })).toBe(false);
	});
});
