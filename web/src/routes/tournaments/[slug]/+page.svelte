<script lang="ts">
	import TournamentGameRow from '$lib/components/tournaments/TournamentGameRow.svelte';
	import { Separator } from '$lib/components/ui/separator';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { formatTournamentDateTime } from '$lib/time/tournament-time';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>{data.tournament.name} · {m.app_title()}</title>
	<meta
		name="description"
		content={data.tournament.description || m.tournament_detail_meta_description()}
	/>
</svelte:head>

<article>
	<header class="grid border border-(--line) lg:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.45fr)]">
		<div class="p-5 sm:p-7 lg:p-9">
			<p class="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
				{m.tournament_label()}
			</p>
			<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
				{data.tournament.name}
			</h1>
			{#if data.tournament.description}
				<p class="mt-5 max-w-3xl text-base leading-7 text-(--text-muted)">
					{data.tournament.description}
				</p>
			{/if}
		</div>

		<dl
			class="grid gap-px border-t border-(--line) bg-(--line) text-sm sm:grid-cols-3 lg:grid-cols-1 lg:border-l lg:border-t-0"
		>
			<div class="bg-(--surface-muted) p-4 sm:p-5">
				<dt class="text-xs text-(--text-muted)">{m.tournament_location()}</dt>
				<dd class="mt-1 font-medium">
					{data.tournament.location || m.tournament_location_tba()}
				</dd>
			</div>
			<div class="bg-(--surface-muted) p-4 sm:p-5">
				<dt class="text-xs text-(--text-muted)">{m.tournament_starts()}</dt>
				<dd class="font-mono-data mt-1 text-xs font-medium">
					{#if data.tournament.starts_at}
						<time datetime={data.tournament.starts_at}>
							{formatTournamentDateTime(
								data.tournament.starts_at,
								getLocale(),
								data.displayTimeZone
							)}
						</time>
					{:else}
						{m.tournament_schedule_tba()}
					{/if}
				</dd>
			</div>
			<div class="bg-(--surface-muted) p-4 sm:p-5">
				<dt class="text-xs text-(--text-muted)">{m.tournament_ends()}</dt>
				<dd class="font-mono-data mt-1 text-xs font-medium">
					{#if data.tournament.ends_at}
						<time datetime={data.tournament.ends_at}>
							{formatTournamentDateTime(data.tournament.ends_at, getLocale(), data.displayTimeZone)}
						</time>
					{:else}
						{m.tournament_schedule_tba()}
					{/if}
				</dd>
			</div>
		</dl>
	</header>

	<section class="mt-9" aria-labelledby="configured-games-heading">
		<header class="flex items-center gap-3 pb-4">
			<span class="bracket-node" aria-hidden="true"></span>
			<div>
				<p class="text-xs font-semibold uppercase tracking-[0.14em] text-(--text-muted)">
					{m.tournament_games()}
				</p>
				<h2 class="font-heading mt-1 text-2xl font-semibold" id="configured-games-heading">
					{m.configured_games_heading()}
				</h2>
			</div>
		</header>
		<Separator class="mb-4" />

		{#if data.tournament.tournament_games.length > 0}
			<div class="flex flex-col gap-4">
				{#each data.tournament.tournament_games as game (game.id)}
					<TournamentGameRow
						tournament={data.tournament}
						{game}
						displayTimeZone={data.displayTimeZone}
					/>
				{/each}
			</div>
		{:else}
			<p
				class="border border-(--line) bg-(--surface-muted) p-6 text-sm text-(--text-muted)"
				role="status"
			>
				{m.empty_tournament_games()}
			</p>
		{/if}
	</section>
</article>
