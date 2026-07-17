<script lang="ts">
	import { invalidate } from '$app/navigation';
	import AppShell from '$lib/components/layout/AppShell.svelte';
	import {
		createDisplayTimeZoneCookie,
		detectDisplayTimeZone,
		DISPLAY_TIME_ZONE_DEPENDENCY
	} from '$lib/time/tournament-time';
	import { onMount } from 'svelte';
	import type { LayoutProps } from './$types';
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children, data }: LayoutProps = $props();

	onMount(() => {
		const detectedTimeZone = detectDisplayTimeZone();
		if (detectedTimeZone === data.displayTimeZone) return;

		document.cookie = createDisplayTimeZoneCookie(detectedTimeZone);
		void invalidate(DISPLAY_TIME_ZONE_DEPENDENCY);
	});
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<AppShell>
	{@render children()}
</AppShell>
