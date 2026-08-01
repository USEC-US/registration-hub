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
		variant?: 'grid' | 'featured';
	}

	let { tournament, displayTimeZone, headingLevel = 2, variant = 'grid' }: Props = $props();
	const tournamentHref = $derived(resolve(localizeInternalHref(`/tournaments/${tournament.slug}`)));
	const headingId = $derived(`tournament-${tournament.id}-title`);
</script>

{#if variant === 'featured'}
	<article class="col-span-full">
		<a
			class="group block rounded-(--radius) focus-visible:outline focus-visible:outline-offset-2 focus-visible:outline-ring"
			href={tournamentHref}
			aria-label={tournament.name}
		>
			{#if tournament.cover_image}
				<figure class="aspect-video max-h-[28rem] overflow-hidden rounded-t-(--radius) bg-muted">
					<img
						class="h-full w-full object-cover"
						src={tournament.cover_image}
						alt={m.tournament_cover_alt({ name: tournament.name })}
						loading="eager"
					/>
				</figure>
			{/if}
			<Card.Root class="grid gap-0 py-0 transition-shadow group-hover:shadow-sm md:grid-cols-[minmax(0,1fr)_17rem]">
				<Card.Header class="p-5 sm:p-6 md:row-span-2">
					<p class="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
						{m.tournament_label()}
					</p>
					<Card.Title>
						{#if headingLevel === 3}
							<h3 id={headingId}>{tournament.name}</h3>
						{:else}
							<h2 id={headingId}>{tournament.name}</h2>
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
					<span class="flex items-center gap-4 text-sm font-semibold text-primary">
						{m.action_view_tournament()}
						<span class="bracket-node" aria-hidden="true"></span>
					</span>
				</Card.Footer>
			</Card.Root>
		</a>
	</article>
{:else}
	<article>
		<a
			class="group block h-full rounded-(--radius) focus-visible:outline focus-visible:outline-offset-2 focus-visible:outline-ring"
			href={tournamentHref}
			aria-label={tournament.name}
		>
			<Card.Root class="flex h-full flex-col gap-0 py-0 transition-shadow group-hover:shadow-sm">
				{#if tournament.cover_image}
					<figure class="aspect-video max-h-56 overflow-hidden rounded-t-(--radius) bg-muted">
						<img
							class="h-full w-full object-cover"
							src={tournament.cover_image}
							alt={m.tournament_cover_alt({ name: tournament.name })}
							loading="lazy"
						/>
					</figure>
				{/if}
				<Card.Header class="flex-1 p-4 sm:p-5">
					<p class="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
						{m.tournament_label()}
					</p>
					<Card.Title>
						{#if headingLevel === 3}
							<h3 id={headingId}>{tournament.name}</h3>
						{:else}
							<h2 id={headingId}>{tournament.name}</h2>
						{/if}
					</Card.Title>
					{#if tournament.description}
						<Card.Description class="line-clamp-3 leading-6">
							{tournament.description}
						</Card.Description>
					{/if}
				</Card.Header>
				<Card.Content class="p-0 border-t-2">
					<dl class="grid grid-cols-2 gap-px bg-border text-sm">
						<div class="bg-card p-4">
							<dt class="text-xs text-muted-foreground">{m.tournament_location()}</dt>
							<dd class="mt-1 font-medium">{tournament.location || m.tournament_location_tba()}</dd>
						</div>
						<div class="bg-card p-4">
							<dt class="text-xs text-muted-foreground">{m.tournament_games()}</dt>
							<dd class="font-mono-data mt-1 font-medium">{tournament.tournament_games.length}</dd>
						</div>
						<div class="col-span-2 bg-card p-4">
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
					</dl>
				</Card.Content>
				<Card.Footer class="justify-between gap-4 border-t px-4 py-4">
					<span class="flex items-center gap-4 text-sm font-semibold text-primary">
						{m.action_view_tournament()}
						<span class="bracket-node" aria-hidden="true"></span>
					</span>
				</Card.Footer>
			</Card.Root>
		</a>
	</article>
{/if}
