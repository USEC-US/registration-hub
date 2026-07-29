import { beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
import { refreshAccessToken, registerAccount, signIn } from './auth';
import { requestJson } from './client';

vi.mock('./client', () => ({ requestJson: vi.fn() }));

describe('auth api', () => {
	beforeEach(() => {
		vi.mocked(requestJson).mockReset();
	});

	it('refreshes an access token with the refresh endpoint', async () => {
		const response = { access: 'new-access-token' };
		vi.mocked(requestJson).mockResolvedValue(response);

		await expect(refreshAccessToken('refresh-token')).resolves.toEqual(response);
		expect(requestJson).toHaveBeenCalledWith('/auth/token/refresh/', {
			method: 'POST',
			body: { refresh: 'refresh-token' }
		});
	});

	it('sends a turnstile token during account registration', async () => {
		vi.mocked(requestJson).mockResolvedValue({} as never);

		await registerAccount(
			{
				email: 'player@example.com',
				password: 'strong-password',
				first_name: 'Player',
				last_name: 'One',
				institution_id: 1
			},
			'turnstile-token'
		);

		expect(requestJson).toHaveBeenCalledWith('/auth/register/', {
			method: 'POST',
			body: {
				email: 'player@example.com',
				password: 'strong-password',
				first_name: 'Player',
				last_name: 'One',
				institution_id: 1,
				turnstile_token: 'turnstile-token'
			}
		});
	});

	it('sends a turnstile token during sign in', async () => {
		vi.mocked(requestJson).mockResolvedValue({ access: 'access', refresh: 'refresh' });

		await signIn('player@example.com', 'strong-password', 'turnstile-token');

		expect(requestJson).toHaveBeenCalledWith('/auth/token/', {
			method: 'POST',
			body: {
				email: 'player@example.com',
				password: 'strong-password',
				turnstile_token: 'turnstile-token'
			}
		});
	});

	it('requires Turnstile tokens for protected auth requests', () => {
		expectTypeOf(registerAccount).parameters.toEqualTypeOf<[
			payload: Parameters<typeof registerAccount>[0],
			turnstileToken: string
		]>();
		expectTypeOf(signIn).parameters.toEqualTypeOf<[
			email: string,
			password: string,
			turnstileToken: string
		]>();
		expect(registerAccount).toBeTypeOf('function');
	});
});
