import { render } from 'vitest-browser-svelte';
import { beforeEach, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import TurnstileWidget from './TurnstileWidget.svelte';

const dependencies = vi.hoisted(() => ({
	env: {} as Record<string, string>,
	render: vi.fn()
}));
let appendChildSpy: ReturnType<typeof vi.spyOn> | null = null;
let preventedTurnstileScriptSrcs: string[] = [];

vi.mock('$app/environment', () => ({ dev: true, browser: true }));
vi.mock('$env/dynamic/public', () => ({ env: dependencies.env }));

beforeEach(() => {
	appendChildSpy?.mockRestore();
	preventedTurnstileScriptSrcs = [];
	const appendChild = document.head.appendChild.bind(document.head);
	appendChildSpy = vi.spyOn(document.head, 'appendChild').mockImplementation((node) => {
		if (node instanceof HTMLScriptElement) {
			const src = node.getAttribute('src') ?? '';
			if (src.startsWith('https://challenges.cloudflare.com/turnstile/')) {
				preventedTurnstileScriptSrcs.push(src);
				node.removeAttribute('src');
			}
		}
		return appendChild(node);
	});
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
	expect(preventedTurnstileScriptSrcs).toEqual([
		'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
	]);
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
	dependencies.render.mockReturnValue('widget-id');
	window.turnstile = { render: dependencies.render, reset: vi.fn() };
	let token = '';

	const widget = render(TurnstileWidget, {
		action: 'sign-in',
		get token() {
			return token;
		},
		set token(value) {
			token = value;
		}
	});

	await vi.waitFor(() => expect(dependencies.render).toHaveBeenCalledOnce());
	const options = dependencies.render.mock.calls[0][1];
	expect(options.action).toBe('sign-in');
	options.callback('verified-token');
	expect(token).toBe('verified-token');
	options['expired-callback']();
	expect(token).toBe('');
	options.callback('replacement-token');
	options['error-callback']();
	expect(token).toBe('');

	widget.component.reset();
	expect(window.turnstile.reset).toHaveBeenCalledWith('widget-id');
});
