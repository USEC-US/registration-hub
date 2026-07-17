import { beforeEach, describe, expect, it, vi } from 'vitest';
import { refreshAccessToken } from './auth';
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
});
