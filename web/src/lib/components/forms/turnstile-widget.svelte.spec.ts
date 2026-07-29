import { render } from 'vitest-browser-svelte';
import { beforeEach, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import TurnstileWidget from './TurnstileWidget.svelte';

const dependencies = vi.hoisted(() => ({
	env: {} as Record<string, string>,
	render: vi.fn()
}));

vi.mock('$app/environment', () => ({ dev: true, browser: true }));
vi.mock('$env/dynamic/public', () => ({ env: dependencies.env }));

beforeEach(() => {
	document.body.innerHTML = '';
	document.head.querySelectorAll('script[data-turnstile-api]').forEach((script) => script.remove());
	dependencies.env.PUBLIC_TURNSTILE_SITE_KEY = '';
	dependencies.render.mockReset();
	window.turnstile = undefined;
});

it('renders a development warning when the site key is missing', async () => {
	let token = '';
	render(TurnstileWidget, {
		action: 'sign-in',
		get token() {
			return token;
		},
		set token(value) {
			token = value;
		}
	});

	await expect.element(page.getByText(/PUBLIC_TURNSTILE_SITE_KEY/)).toBeVisible();
	expect(token).not.toBe('');
});

it('appends one pending Turnstile script and renders after it loads with a configured key', async () => {
	dependencies.env.PUBLIC_TURNSTILE_SITE_KEY = 'site-key';

	render(TurnstileWidget, { action: 'sign-in', token: '' });

	await vi.waitFor(() =>
		expect(document.head.querySelectorAll('script[data-turnstile-api]')).toHaveLength(1)
	);
	const script = document.head.querySelector<HTMLScriptElement>('script[data-turnstile-api]');
	expect(script).not.toBeNull();
	expect(dependencies.render).not.toHaveBeenCalled();

	window.turnstile = { render: dependencies.render };
	script!.dispatchEvent(new Event('load'));

	await vi.waitFor(() => expect(dependencies.render).toHaveBeenCalledOnce());
});

it('renders immediately for a later mount when the Turnstile script is already ready', async () => {
	dependencies.env.PUBLIC_TURNSTILE_SITE_KEY = 'site-key';
	const script = document.createElement('script');
	script.dataset.turnstileApi = 'true';
	document.head.appendChild(script);
	window.turnstile = { render: dependencies.render };

	render(TurnstileWidget, { action: 'sign-in', token: '' });

	await vi.waitFor(() => expect(dependencies.render).toHaveBeenCalledOnce());
});
