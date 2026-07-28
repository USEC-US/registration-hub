import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { createRawSnippet } from 'svelte';
import type { CurrentUser } from '$lib/api/types';
import * as m from '$lib/paraglide/messages';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import AppShell from './AppShell.svelte';

const authStateMock = vi.hoisted(() => ({
	status: 'idle',
	currentUser: null as CurrentUser | null,
	initialize: vi.fn()
}));

vi.mock('$env/dynamic/public', () => ({ env: {} }));
vi.mock('$app/state', () => ({
	page: { url: new URL('https://usec.test/tournaments') }
}));
vi.mock('$lib/states/auth-state.svelte', () => ({ authState: authStateMock }));

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
	authStateMock.status = 'idle';
	authStateMock.currentUser = null;
	authStateMock.initialize.mockReset().mockResolvedValue(null);
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

	it('lets public navigation cells grow with configurable minimum widths', async () => {
		renderShell();

		const tournaments = page.getByRole('link', { name: m.nav_tournaments() });
		const rules = page.getByText('Rules');
		await expect.element(tournaments).toHaveClass('flex-1');
		await expect.element(rules).toHaveClass('flex-1');
		expect(
			(tournaments.elements()[0] as HTMLElement).style.getPropertyValue('--nav-cell-min')
		).toBe('9rem');
		expect((rules.elements()[0] as HTMLElement).style.getPropertyValue('--nav-cell-min')).toBe(
			'7rem'
		);
	});

	it('renders sign-in, register, and the current language in a radio dropdown without a session', async () => {
		authStateMock.status = 'signed-out';
		renderShell();

		await expect.element(page.getByRole('link', { name: m.nav_sign_in() })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Register' })).toBeVisible();
		const localeTrigger = page.getByRole('button', { name: m.locale_switcher_label() });
		await expect.element(localeTrigger).toHaveTextContent(m.locale_name_en());
		await localeTrigger.click();
		await expect
			.element(page.getByRole('menuitemradio', { name: m.locale_name_en() }))
			.toHaveAttribute('aria-checked', 'true');
		await expect
			.element(page.getByRole('menuitemradio', { name: m.locale_name_vi() }))
			.toHaveAttribute('aria-checked', 'false');
	});

	it('uses English name order for the signed-in welcome link', async () => {
		authStateMock.status = 'signed-in';
		authStateMock.currentUser = user;
		authStateMock.initialize.mockResolvedValue(user);
		const { container } = renderShell();

		await expect
			.element(page.getByRole('link', { name: m.nav_welcome({ name: 'Thắng Nguyễn Hữu Quốc' }) }))
			.toBeVisible();
		await expect.element(page.getByRole('link', { name: m.nav_my_registrations() })).toBeVisible();
		expect(authStateMock.initialize).toHaveBeenCalledOnce();
		expect(container.querySelector('a[href="/auth/sign-in"]')).toBeNull();
		expect(container.querySelector('a[href="/auth/register"]')).toBeNull();
	});

	it('uses Vietnamese name order for the signed-in welcome link', async () => {
		overwriteGetLocale(() => 'vi');
		authStateMock.status = 'signed-in';
		authStateMock.currentUser = user;
		authStateMock.initialize.mockResolvedValue(user);

		renderShell();

		await expect
			.element(page.getByRole('link', { name: m.nav_welcome({ name: 'Nguyễn Hữu Quốc Thắng' }) }))
			.toBeVisible();
		expect(authStateMock.initialize).toHaveBeenCalledOnce();
	});

	it('renders public account controls from shared signed-out state', async () => {
		authStateMock.status = 'signed-out';
		renderShell();

		await expect.element(page.getByRole('link', { name: m.nav_sign_in() })).toBeVisible();
		await expect.element(page.getByRole('link', { name: m.nav_register() })).toBeVisible();
	});

	it('keeps account controls unavailable from shared unavailable state', () => {
		authStateMock.status = 'unavailable';
		const { container } = renderShell();

		expect(container.querySelector('a[href="/auth/sign-in"]')).toBeNull();
		expect(container.querySelector('a[href="/auth/register"]')).toBeNull();
	});
});
