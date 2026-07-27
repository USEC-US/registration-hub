import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { createRawSnippet } from 'svelte';
import { ApiRequestError } from '$lib/api/client';
import { getCurrentUser } from '$lib/api/auth';
import type { CurrentUser } from '$lib/api/types';
import { clearSession, getAccessToken } from '$lib/auth/session';
import * as m from '$lib/paraglide/messages';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import AppShell from './AppShell.svelte';

vi.mock('$env/dynamic/public', () => ({ env: {} }));
vi.mock('$app/state', () => ({
	page: { url: new URL('https://usec.test/tournaments') }
}));
vi.mock('$lib/api/auth', () => ({ getCurrentUser: vi.fn() }));
vi.mock('$lib/auth/session', () => ({
	clearSession: vi.fn(),
	getAccessToken: vi.fn()
}));

const children = createRawSnippet(() => ({ render: () => '<p>Page content</p>' }));
const user: CurrentUser = {
	id: 7,
	email: 'thang@example.com',
	first_name: 'Thắng',
	last_name: 'Nguyễn Hữu Quốc',
	school: 'HCMUS'
};

function renderShell() {
	return render(AppShell, { children });
}

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	vi.mocked(getAccessToken).mockReset().mockReturnValue(null);
	vi.mocked(getCurrentUser).mockReset();
	vi.mocked(clearSession).mockReset();
});

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('AppShell secondary navigation', () => {
	it('renders a compact public row below the brand header', async () => {
		renderShell();

		await expect.element(page.getByRole('link', { name: m.nav_tournaments() })).toBeVisible();
		const rules = page.getByText('Rules');
		await expect.element(rules).toBeVisible();
		await expect.element(rules).toHaveAttribute('aria-disabled', 'true');
	});

	it('renders sign-in, register, and the locale selector without a session', async () => {
		renderShell();

		await expect.element(page.getByRole('link', { name: m.nav_sign_in() })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Register' })).toBeVisible();
		await expect
			.element(page.getByRole('combobox', { name: m.locale_switcher_label() }))
			.toBeVisible();
	});

	it('uses English name order for the signed-in welcome link', async () => {
		vi.mocked(getAccessToken).mockReturnValue('access-token');
		vi.mocked(getCurrentUser).mockResolvedValue(user);
		const { container } = renderShell();

		await expect
			.element(page.getByRole('link', { name: m.nav_welcome({ name: 'Thắng Nguyễn Hữu Quốc' }) }))
			.toBeVisible();
		await expect.element(page.getByRole('link', { name: m.nav_my_registrations() })).toBeVisible();
		expect(container.querySelector('a[href="/auth/sign-in"]')).toBeNull();
		expect(container.querySelector('a[href="/auth/register"]')).toBeNull();
	});

	it('uses Vietnamese name order for the signed-in welcome link', async () => {
		overwriteGetLocale(() => 'vi');
		vi.mocked(getAccessToken).mockReturnValue('access-token');
		vi.mocked(getCurrentUser).mockResolvedValue(user);

		renderShell();

		await expect
			.element(page.getByRole('link', { name: m.nav_welcome({ name: 'Nguyễn Hữu Quốc Thắng' }) }))
			.toBeVisible();
	});

	it.each([401, 403])('clears a stale %i session and renders signed-out controls', async (status) => {
		vi.mocked(getAccessToken).mockReturnValue('access-token');
		vi.mocked(getCurrentUser).mockRejectedValue(new ApiRequestError(status, 'Unauthorized'));

		renderShell();

		await vi.waitFor(() => expect(clearSession).toHaveBeenCalledOnce());
		expect(getCurrentUser).toHaveBeenCalledWith('access-token');
		await expect.element(page.getByRole('link', { name: m.nav_sign_in() })).toBeVisible();
		await expect.element(page.getByRole('link', { name: m.nav_register() })).toBeVisible();
	});

	it('keeps account controls unavailable for a non-authentication error', async () => {
		vi.mocked(getAccessToken).mockReturnValue('access-token');
		vi.mocked(getCurrentUser).mockRejectedValue(new ApiRequestError(500, 'Server error'));
		const { container } = renderShell();

		await vi.waitFor(() => expect(getCurrentUser).toHaveBeenCalledWith('access-token'));
		expect(clearSession).not.toHaveBeenCalled();
		expect(container.querySelector('a[href="/auth/sign-in"]')).toBeNull();
		expect(container.querySelector('a[href="/auth/register"]')).toBeNull();
	});
});
