<script lang="ts">
	import { resolve } from '$app/paths';
	import type { PublicTournament } from '$lib/api/types';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { formatTournamentDate } from '$lib/time/tournament-time';
	import * as Card from '$lib/components/ui/card';

	interface Props {
		tournament: PublicTournament;
		displayTimeZone: string;
		headingLevel?: 2 | 3;
	}

	let { tournament, displayTimeZone, headingLevel = 2 }: Props = $props();
</script>

<article>
	<Card.Root class="grid gap-0 py-0 md:grid-cols-[minmax(0,1fr)_17rem]">
		<Card.Header class="p-5 sm:p-6 md:row-span-2">
			<p class="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
				{m.tournament_label()}
			</p>
			<Card.Title>
				{#if headingLevel === 3}
					<h3><a href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}>{tournament.name}</a></h3>
				{:else}
					<h2><a href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}>{tournament.name}</a></h2>
				{/if}
			</Card.Title>
			{#if tournament.description}
				<Card.Description class="max-w-2xl leading-6">{tournament.description}</Card.Description>
			{/if}
		</Card.Header>

		<Card.Content class="p-0">
			<dl class="grid grid-cols-2 gap-px bg-border text-sm md:grid-cols-1">
				<div class="bg-muted p-4">
					<dt class="text-xs text-muted-foreground">{m.tournament_dates()}</dt>
					<dd class="font-mono-data mt-1 text-xs font-medium">
						{#if !tournament.starts_at && !tournament.ends_at}
							{m.tournament_schedule_tba()}
						{:else}
							{#if tournament.starts_at}
								<time datetime={tournament.starts_at}>
									{formatTournamentDate(tournament.starts_at, getLocale(), displayTimeZone)}
								</time>
							{/if}
							{#if tournament.starts_at && tournament.ends_at}—{/if}
							{#if tournament.ends_at}
								<time datetime={tournament.ends_at}>
									{formatTournamentDate(tournament.ends_at, getLocale(), displayTimeZone)}
								</time>
							{/if}
						{/if}
					</dd>
				</div>
				<div class="bg-muted p-4">
					<dt class="text-xs text-muted-foreground">{m.tournament_location()}</dt>
					<dd class="mt-1 font-medium">{tournament.location || m.tournament_location_tba()}</dd>
				</div>
				<div class="col-span-2 bg-muted p-4 md:col-span-1">
					<dt class="text-xs text-muted-foreground">{m.tournament_games()}</dt>
					<dd class="font-mono-data mt-1 font-medium">{tournament.tournament_games.length}</dd>
				</div>
			</dl>
		</Card.Content>
		<Card.Footer class="justify-between gap-4 border-t px-4 py-4">
			<a
				class="group/action flex items-center gap-4 text-sm font-semibold text-primary"
				href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}
			>
				{m.action_view_tournament()}
				<span class="bracket-node" aria-hidden="true"></span>
			</a>
		</Card.Footer>
	</Card.Root>
</article>
