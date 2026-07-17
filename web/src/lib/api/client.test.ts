import { describe, expect, expectTypeOf, it, vi } from 'vitest';
import { ApiRequestError, requestJson } from './client';
import type { ApiRequestOptions } from './client';

vi.mock('$app/environment', () => ({ dev: false }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

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

	it('normalizes top-level error lists', async () => {
		const fetcher = vi.fn().mockResolvedValue(
			new Response(JSON.stringify(['Registration is closed.', 'Choose another tournament.']), {
				status: 400,
				headers: { 'content-type': 'application/json' }
			})
		);

		await expect(
			requestJson('/example/', { baseUrl: 'http://api.test', fetcher })
		).rejects.toMatchObject({
			status: 400,
			nonFieldErrors: ['Registration is closed.', 'Choose another tournament.']
		} satisfies Partial<ApiRequestError>);
	});

	it('flattens nested field error leaves with their paths', async () => {
		const fetcher = vi.fn().mockResolvedValue(
			new Response(
				JSON.stringify({
					members: [
						{
							gamer_tag_snapshot: ['This field is required.'],
							school_snapshot: ['Ensure this field has no more than 128 characters.']
						},
						{ non_field_errors: ['A captain is required.'] }
					]
				}),
				{ status: 400, headers: { 'content-type': 'application/json' } }
			)
		);

		await expect(
			requestJson('/example/', { baseUrl: 'http://api.test', fetcher })
		).rejects.toMatchObject({
			fieldErrors: {
				members: [
					'[0].gamer_tag_snapshot: This field is required.',
					'[0].school_snapshot: Ensure this field has no more than 128 characters.',
					'[1].non_field_errors: A captain is required.'
				]
			}
		} satisfies Partial<ApiRequestError>);
	});

	it('passes FormData without forcing a content type', async () => {
		const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
		const formData = new FormData();
		formData.set('proof_file', new Blob(['proof']), 'proof.txt');

		await requestJson('/example/', {
			method: 'POST',
			baseUrl: 'http://api.test',
			body: formData,
			fetcher
		});

		const [, init] = fetcher.mock.calls[0];
		expect(init?.body).toBe(formData);
		expect((init?.headers as Headers).has('content-type')).toBe(false);
	});

	it('preserves a caller-provided content type for json bodies', async () => {
		const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

		await requestJson('/example/', {
			method: 'POST',
			baseUrl: 'http://api.test',
			body: { ok: true },
			headers: { 'content-type': 'application/merge-patch+json' },
			fetcher
		});

		const [, init] = fetcher.mock.calls[0];
		expect((init?.headers as Headers).get('content-type')).toBe(
			'application/merge-patch+json'
		);
	});

	it('requires an api base url outside development', async () => {
		const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

		await expect(requestJson('/example/', { fetcher })).rejects.toThrow(
			'PUBLIC_API_BASE_URL is required outside development.'
		);

		expect(fetcher).not.toHaveBeenCalled();
	});

	it('advertises only supported request body kinds', () => {
		expectTypeOf<ApiRequestOptions>().toMatchTypeOf<{
			body?: FormData | object | null;
		}>();
		expect({ body: new FormData() } satisfies ApiRequestOptions).toBeDefined();
	});
});
