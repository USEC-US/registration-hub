<script lang="ts">
	import { browser } from '$app/environment';
	import { getTurnstileSiteKey, type TurnstileAction } from '$lib/turnstile/config';
	import * as m from '$lib/paraglide/messages';
	import { onMount } from 'svelte';

	export const DEVELOPMENT_TURNSTILE_BYPASS_TOKEN = 'development-turnstile-bypass';

	interface Props {
		action: TurnstileAction;
		token: string;
	}

	let { action, token = $bindable('') }: Props = $props();
	let container: HTMLDivElement | null = $state(null);
	let siteKey = $state('');
	let warning = $state('');
	let error = $state('');
	let widgetId = $state<string | null>(null);
	let retryWidget = $state<() => void>(() => {});

	export function reset(): void {
		token = siteKey ? '' : DEVELOPMENT_TURNSTILE_BYPASS_TOKEN;
		error = '';
		if (widgetId) window.turnstile?.reset?.(widgetId);
	}

	onMount(() => {
		siteKey = getTurnstileSiteKey();
		if (!siteKey) {
			token = DEVELOPMENT_TURNSTILE_BYPASS_TOKEN;
			warning = m.turnstile_dev_missing_key();
			return;
		}
		if (!browser || !container) return;
		const target = container;
		let script: HTMLScriptElement | null = null;

		const renderWidget = () => {
			try {
				widgetId = window.turnstile?.render(target, {
					sitekey: siteKey,
					action,
					callback: (value: string) => {
						token = value;
						error = '';
					},
					'expired-callback': () => {
						token = '';
					},
					'error-callback': () => {
						token = '';
						error = m.turnstile_challenge_error();
					},
					'unsupported-callback': () => {
						token = '';
						error = m.turnstile_unsupported();
					}
				}) ?? null;
			} catch {
				token = '';
				error = m.turnstile_challenge_error();
			}
		};

		const handleScriptLoad = () => renderWidget();
		const handleScriptError = () => {
			token = '';
			error = m.turnstile_script_load_error();
		};
		const loadWidget = () => {
			const existing = document.querySelector<HTMLScriptElement>('script[data-turnstile-api]');
			script = existing ?? document.createElement('script');
			if (!existing) {
				Object.assign(script, {
					src: 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit',
					async: true,
					defer: true
				});
				script.dataset.turnstileApi = 'true';
				document.head.appendChild(script);
			}

			if (window.turnstile) {
				renderWidget();
				return;
			}
			script.addEventListener('load', handleScriptLoad, { once: true });
			script.addEventListener('error', handleScriptError, { once: true });
		};

		retryWidget = () => {
			token = '';
			error = '';
			if (widgetId && window.turnstile?.reset) {
				window.turnstile.reset(widgetId);
				return;
			}
			script?.remove();
			widgetId = null;
			loadWidget();
		};

		loadWidget();

		return () => {
			script?.removeEventListener('load', handleScriptLoad);
			script?.removeEventListener('error', handleScriptError);
			retryWidget = () => {};
		};
	});
</script>

<div class="grid gap-2">
	<div bind:this={container} data-turnstile-action={action}></div>
	{#if warning}
		<p class="text-xs text-warning" role="status">{warning}</p>
	{/if}
	{#if error}
		<p class="text-sm text-error" role="alert">{error}</p>
		<button class="btn btn-sm btn-outline w-fit" type="button" onclick={retryWidget}>
			{m.turnstile_retry()}
		</button>
	{/if}
</div>
