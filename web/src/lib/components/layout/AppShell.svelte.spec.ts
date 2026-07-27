import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { createRawSnippet } from 'svelte';
import { getCurrentUser } from '$lib/api/auth';
import { getAccessToken } from '$lib/auth/session';
import * as m from '$lib/paraglide/messages';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import AppShell from './AppShell.svelte';

vi.mock('$app/state', () => ({
	page: { url: new URL('https://usec.test/tournaments') }
}));
vi.mock('$lib/api/auth', () => ({ getCurrentUser: vi.fn() }));
vi.mock('$lib/auth/session', () => ({
	clearSession: vi.fn(),
	getAccessToken: vi.fn()
}));

const children = createRawSnippet(() => ({ render: () => '<p>Page content</p>' }));

function renderShell() {
	return render(AppShell, { children });
}

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	vi.mocked(getAccessToken).mockReset().mockReturnValue(null);
	vi.mocked(getCurrentUser).mockReset();
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
});
