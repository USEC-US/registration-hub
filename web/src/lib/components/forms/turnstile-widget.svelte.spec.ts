import { render } from 'vitest-browser-svelte';
import { beforeEach, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import TurnstileWidget from './TurnstileWidget.svelte';

vi.mock('$app/environment', () => ({ dev: true, browser: true }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

beforeEach(() => {
	document.body.innerHTML = '';
});

it('renders a development warning when the site key is missing', async () => {
	render(TurnstileWidget, { action: 'sign-in', token: '' });

	await expect.element(page.getByText(/PUBLIC_TURNSTILE_SITE_KEY/)).toBeVisible();
});
