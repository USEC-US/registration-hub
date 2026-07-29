<script lang="ts">
	import { browser } from '$app/environment';
	import { getTurnstileSiteKey, type TurnstileAction } from '$lib/turnstile/config';
	import * as m from '$lib/paraglide/messages';
	import { onMount } from 'svelte';

	interface Props {
		action: TurnstileAction;
		token: string;
	}

	let { action, token = $bindable('') }: Props = $props();
	let container: HTMLDivElement | null = $state(null);
	let siteKey = $state('');
	let warning = $state('');

	onMount(() => {
		siteKey = getTurnstileSiteKey();
		if (!siteKey) {
			warning = m.turnstile_dev_missing_key();
			return;
		}
		if (!browser || !container) return;
		const target = container;

		const existing = document.querySelector<HTMLScriptElement>('script[data-turnstile-api]');
		const script = existing ?? document.createElement('script');
		if (!existing) {
			Object.assign(script, {
				src: 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit',
				async: true,
				defer: true
			});
			script.dataset.turnstileApi = 'true';
			document.head.appendChild(script);
		}

		const renderWidget = () => {
			window.turnstile?.render(target, {
				sitekey: siteKey,
				action,
				callback: (value: string) => {
					token = value;
				},
				'expired-callback': () => {
					token = '';
				},
				'error-callback': () => {
					token = '';
				}
			});
		};

		if (window.turnstile) {
			renderWidget();
		} else {
			script.addEventListener('load', renderWidget, { once: true });
		}
	});
</script>

<div class="grid gap-2">
	<div bind:this={container} data-turnstile-action={action}></div>
	{#if warning}
		<p class="text-xs text-warning" role="status">{warning}</p>
	{/if}
</div>
