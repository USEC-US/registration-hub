<script lang="ts">
	import AppShell from '$lib/components/layout/AppShell.svelte';
	import type { Snippet } from 'svelte';
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children }: { children: Snippet } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<AppShell>
	{@render children()}
</AppShell>
