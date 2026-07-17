import { describe, expect, it, vi } from 'vitest';
import { ApiRequestError, requestJson } from './client';

describe('requestJson', () => {
	it('adds bearer token and parses json responses', async () => {
		const fetcher = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ ok: true }), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			})
		);

		const result = await requestJson<{ ok: boolean }>('/example/', {
			accessToken: 'token',
			baseUrl: 'http://api.test',
			fetcher
		});

		expect(result.ok).toBe(true);
		const [, init] = fetcher.mock.calls[0];
		expect(fetcher).toHaveBeenCalledWith('http://api.test/example/', expect.any(Object));
		expect((init?.headers as Headers).get('authorization')).toBe('Bearer token');
	});

	it('normalizes field errors', async () => {
		const fetcher = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ email: ['This field is required.'] }), {
				status: 400,
				headers: { 'content-type': 'application/json' }
			})
		);

		await expect(
			requestJson('/example/', { baseUrl: 'http://api.test', fetcher })
		).rejects.toMatchObject({
			status: 400,
			fieldErrors: { email: ['This field is required.'] }
		} satisfies Partial<ApiRequestError>);
	});
});
