<script lang="ts">
	import { resolve } from '$app/paths';
	import type { PublicTournament } from '$lib/api/types';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';

	interface Props {
		tournament: PublicTournament;
	}

	let { tournament }: Props = $props();

	function formatDate(value: string): string {
		return new Intl.DateTimeFormat(getLocale(), { dateStyle: 'medium' }).format(new Date(value));
	}

	function dateRange(): string {
		if (!tournament.starts_at && !tournament.ends_at) return m.tournament_schedule_tba();
		if (!tournament.starts_at) return formatDate(tournament.ends_at!);
		if (!tournament.ends_at) return formatDate(tournament.starts_at);
		return `${formatDate(tournament.starts_at)} — ${formatDate(tournament.ends_at)}`;
	}
</script>

<article class="grid border border-[var(--line)] bg-white md:grid-cols-[minmax(0,1fr)_17rem]">
	<div class="p-5 sm:p-6">
		<p class="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
			{m.tournament_label()}
		</p>
		<h2 class="font-heading text-2xl font-semibold leading-tight sm:text-3xl">
			<a href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}
				>{tournament.name}</a
			>
		</h2>
		{#if tournament.description}
			<p class="mt-4 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
				{tournament.description}
			</p>
		{/if}
	</div>

	<div
		class="grid border-t border-[var(--line)] bg-[var(--surface-muted)] md:border-l md:border-t-0"
	>
		<dl
			class="grid grid-cols-2 gap-px border-b border-[var(--line)] bg-[var(--line)] text-sm md:grid-cols-1"
		>
			<div class="bg-[var(--surface-muted)] p-4">
				<dt class="text-xs text-[var(--text-muted)]">{m.tournament_dates()}</dt>
				<dd class="font-mono-data mt-1 text-xs font-medium">{dateRange()}</dd>
			</div>
			<div class="bg-[var(--surface-muted)] p-4">
				<dt class="text-xs text-[var(--text-muted)]">{m.tournament_location()}</dt>
				<dd class="mt-1 font-medium">
					{tournament.location || m.tournament_location_online()}
				</dd>
			</div>
			<div class="bg-[var(--surface-muted)] p-4">
				<dt class="text-xs text-[var(--text-muted)]">{m.tournament_games()}</dt>
				<dd class="font-mono-data mt-1 font-medium">{tournament.tournament_games.length}</dd>
			</div>
		</dl>
		<a
			class="group/action flex items-center justify-between gap-4 px-4 py-4 text-sm font-semibold text-[var(--accent)]"
			href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}
		>
			{m.action_view_tournament()}
			<span class="bracket-node" aria-hidden="true"></span>
		</a>
	</div>
</article>
