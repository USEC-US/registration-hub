<script lang="ts">
	import TournamentCard from '$lib/components/tournaments/TournamentCard.svelte';
	import * as m from '$lib/paraglide/messages';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>{m.published_tournaments_heading()} · {m.app_title()}</title>
	<meta name="description" content={m.published_tournaments_intro()} />
</svelte:head>

<header class="grid border border-[var(--line)] lg:grid-cols-[minmax(0,1.6fr)_minmax(14rem,0.4fr)]">
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
			{m.tournament_label()}
		</p>
		<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
			{m.published_tournaments_heading()}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-[var(--text-muted)]">
			{m.published_tournaments_intro()}
		</p>
	</div>
	<div
		class="flex items-end border-t border-[var(--line)] bg-[var(--surface-muted)] p-5 lg:border-l lg:border-t-0 lg:p-7"
	>
		<p class="font-mono-data text-xs leading-5 text-[var(--text-muted)]">
			{m.published_tournaments_note()}
		</p>
	</div>
</header>

{#if data.tournaments.length > 0}
	<section class="mt-8 space-y-4" aria-label={m.published_tournaments_heading()}>
		{#each data.tournaments as tournament (tournament.id)}
			<TournamentCard {tournament} />
		{/each}
	</section>
{:else}
	<p
		class="mt-8 border border-[var(--line)] bg-[var(--surface-muted)] p-6 text-sm text-[var(--text-muted)]"
		role="status"
	>
		{m.empty_tournaments()}
	</p>
{/if}
