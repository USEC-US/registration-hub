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
		const script =
			existing ??
			Object.assign(document.createElement('script'), {
				src: 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit',
				async: true,
				defer: true,
				dataset: { turnstileApi: 'true' }
			});
		if (!existing) document.head.appendChild(script);

		script.addEventListener(
			'load',
			() => {
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
			},
			{ once: true }
		);
	});
</script>

<div class="grid gap-2">
	<div bind:this={container} data-turnstile-action={action}></div>
	{#if warning}
		<p class="text-xs text-warning" role="status">{warning}</p>
	{/if}
</div>
