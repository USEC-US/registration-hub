import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { render } from 'svelte/server';
import SignInPage from './auth/sign-in/+page.svelte';
import RegisterPage from './auth/register/+page.svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ssr } from './account/profile/+page';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/en/auth/register') } }));

it('keeps the localStorage-authenticated profile page client-only', () => {
	expect(ssr).toBe(false);
});

beforeEach(() => overwriteGetLocale(() => 'en'));

// Inspect actual server-rendered markup: onMount has not run and no submit handler is attached.
describe.each([
	['sign-in', SignInPage],
	['account registration', RegisterPage]
] as const)('%s before hydration', (_name, Component) => {
	it('keeps native credential submissions out of the URL', () => {
		const { body } = render(Component);
		expect(body).toMatch(/<input\b[^>]*type="password"/);
		expect(body.match(/<form\b[^>]*>/)?.[0]).toMatch(/method="post"/);
	});
	it('does not enable the credential submit action before its handler is ready', () => {
		const { body } = render(Component);
		const submitButton = body.match(/<button\b(?=[^>]*type="submit")[^>]*>/)?.[0];
		expect(submitButton).toBeDefined();
		expect(submitButton).toMatch(/\bdisabled(?:[\s=>])/);
	});
});
