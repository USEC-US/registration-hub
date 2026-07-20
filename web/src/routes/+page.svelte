<script lang="ts">
	import { resolve } from '$app/paths';
	import TournamentCard from '$lib/components/tournaments/TournamentCard.svelte';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import type { PageProps } from './$types';

  import { ChevronRight } from "@lucide/svelte"

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>{m.app_title()}</title>
	<meta name="description" content={m.home_intro()} />
</svelte:head>

<header class="grid border border-(--line) lg:grid-cols-[minmax(0,1.6fr)_minmax(16rem,0.4fr)]">
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text--accent">
			{m.hero_subtitle()}
		</p>
		<h1 class="font-heading mt-3 max-w-4xl text-3xl font-semibold leading-tight sm:text-5xl">
			{m.hero_title()}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-(--text-muted)">
			{m.home_intro()}
		</p>
	</div>
	<div
		class="flex items-end border-t border-(--line) bg-(--surface-muted) p-5 lg:border-l lg:border-t-0 lg:p-7"
	>
		<a
			class="flex w-full items-center justify-between gap-4 text-sm font-semibold text-accent"
			href={resolve(localizeInternalHref('/tournaments'))}
		>
			{m.action_browse_tournaments()}
      <ChevronRight />
		</a>
	</div>
</header>

<section class="mt-9" aria-labelledby="published-tournaments-heading">
	<header class="mb-4 flex items-center gap-3 border-b border-(--line) pb-4">
		<span class="bracket-node" aria-hidden="true"></span>
		<h2 class="font-heading text-2xl font-semibold" id="published-tournaments-heading">
			{m.published_tournaments_heading()}
		</h2>
	</header>

	{#if data.tournaments.length > 0}
		<div class="space-y-4">
			{#each data.tournaments as tournament (tournament.id)}
				<TournamentCard {tournament} displayTimeZone={data.displayTimeZone} headingLevel={3} />
			{/each}
		</div>
	{:else}
		<p
			class="border border-(--line) bg-(--surface-muted) p-6 text-sm text-(--text-muted)"
			role="status"
		>
			{m.empty_tournaments()}
		</p>
	{/if}
</section>
