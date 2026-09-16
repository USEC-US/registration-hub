<script lang="ts">
	import { resolve } from '$app/paths';
	import * as Alert from '$lib/components/ui/alert';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { formatTournamentDate } from '$lib/time/tournament-time';
	import { ArrowRight, ArrowUpRight, CalendarDays, Gamepad2, MapPin, Trophy } from '@lucide/svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const spotlight = $derived(
		data.tournaments.find((tournament) => tournament.is_featured) ?? data.tournaments[0]
	);
	const spotlightHref = $derived(
		spotlight ? resolve(localizeInternalHref(`/tournaments/${spotlight.slug}`)) : undefined
	);
	const steps = $derived([
		{ title: m.home_step_discover_title(), description: m.home_step_discover_description() },
		{ title: m.home_step_prepare_title(), description: m.home_step_prepare_description() },
		{ title: m.home_step_join_title(), description: m.home_step_join_description() }
	]);
</script>

<svelte:head>
	<title>{m.app_title()}</title>
	<meta name="description" content={m.home_welcome_intro()} />
</svelte:head>

<div class="home-landing">
	<div class="grid items-center gap-10 py-4 sm:py-8 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:py-12">
		<header class="min-w-0">
			<p
				class="mb-6 flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.18em] text-primary"
			>
				<span class="h-px w-8 bg-primary" aria-hidden="true"></span>
				{m.home_welcome_kicker()}
			</p>
			<h1 class="max-w-xl text-4xl font-bold leading-[1.15] sm:text-5xl xl:text-6xl">
				{m.home_welcome_title()}
				<span class="mt-2 block text-primary">{m.home_welcome_title_accent()}</span>
			</h1>
			<p class="mt-6 max-w-lg text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
				{m.home_welcome_intro()}
			</p>
			<div class="mt-8 flex flex-wrap items-center gap-3">
				<Button size="lg" href={resolve(localizeInternalHref('/tournaments'))}>
					{m.action_browse_tournaments()}
					<ArrowRight data-icon="inline-end" aria-hidden="true" />
				</Button>
				<Button variant="ghost" size="lg" href="https://discord.gg/Ztkk8csTck">
					{m.home_join_community()}
					<ArrowUpRight data-icon="inline-end" aria-hidden="true" />
				</Button>
			</div>
			<p class="mt-5 text-sm text-muted-foreground">{m.home_welcome_note()}</p>
		</header>

		<section class="min-w-0" aria-labelledby="home-spotlight-heading">
			<div class="mb-4 flex items-center gap-2 text-primary">
				<Trophy class="size-4" aria-hidden="true" />
				<h2 id="home-spotlight-heading" class="text-sm font-semibold">
					{m.home_spotlight_heading()}
				</h2>
			</div>
			{#if spotlight}
				<article
					class="overflow-hidden rounded-2xl border bg-card shadow-sm"
					aria-labelledby="home-tournament-title"
				>
					<div class="spotlight-art relative aspect-video overflow-hidden border-b">
						{#if spotlight.cover_image}
							<img
								class="absolute inset-0 size-full object-cover"
								src={spotlight.cover_image}
								alt={m.tournament_cover_alt({ name: spotlight.name })}
								fetchpriority="high"
							/>
						{:else}
							<div
								class="absolute inset-0 flex flex-col items-center justify-center gap-3"
								aria-hidden="true"
							>
								<img
									src="/logo/logo.webp"
									alt=""
									class="size-24 object-contain sm:size-28"
									width="112"
									height="112"
								/>
								<span class="font-heading text-xs font-bold tracking-[0.3em] text-primary"
									>USEC · ESPORTS</span
								>
							</div>
						{/if}
					</div>
					<div class="p-5 sm:p-7">
						{#if spotlight.is_featured}
							<Badge variant="secondary">{m.tournament_featured_label()}</Badge>
						{/if}
						<h3
							id="home-tournament-title"
							class="mt-3 wrap-break-word text-2xl font-bold leading-tight sm:text-3xl"
						>
							<a href={spotlightHref}>{spotlight.name}</a>
						</h3>
						{#if spotlight.description}
							<p class="mt-3 line-clamp-2 wrap-break-word text-sm leading-6 text-muted-foreground">
								{@html spotlight.description}
							</p>
						{/if}
						<dl class="mt-5 flex flex-col gap-3 text-sm text-muted-foreground">
							<div class="flex items-start gap-3">
								<dt>
									<CalendarDays class="mt-0.5 size-4" aria-hidden="true" /><span class="sr-only"
										>{m.tournament_dates()}</span
									>
								</dt>
								<dd>
									{#if spotlight.starts_at || spotlight.ends_at}
										{#if spotlight.starts_at}<time datetime={spotlight.starts_at}
												>{formatTournamentDate(
													spotlight.starts_at,
													getLocale(),
													data.displayTimeZone
												)}</time
											>{/if}
										{#if spotlight.starts_at && spotlight.ends_at}
											—
										{/if}
										{#if spotlight.ends_at}<time datetime={spotlight.ends_at}
												>{formatTournamentDate(
													spotlight.ends_at,
													getLocale(),
													data.displayTimeZone
												)}</time
											>{/if}
									{:else}{m.tournament_schedule_tba()}{/if}
								</dd>
							</div>
							<div class="flex items-start gap-3">
								<dt>
									<MapPin class="mt-0.5 size-4" aria-hidden="true" /><span class="sr-only"
										>{m.tournament_location()}</span
									>
								</dt>
								<dd class="min-w-0 wrap-break-word">
									{spotlight.location || m.tournament_location_tba()}
								</dd>
							</div>
						</dl>
						{#if spotlight.tournament_games.length > 0}
							<ul class="mt-5 flex flex-wrap gap-2" aria-label={m.tournament_games()}>
								{#each spotlight.tournament_games as game (game.id)}
									<li class="max-w-full">
										<Badge variant="outline" class="max-w-full"
											><span class="truncate">{game.game_name}</span></Badge
										>
									</li>
								{/each}
							</ul>
						{/if}
						<div class="mt-6">
							<Button variant="outline" href={spotlightHref} class="w-full justify-between"
								>{m.action_view_tournament()}<ArrowRight
									data-icon="inline-end"
									aria-hidden="true"
								/></Button
							>
						</div>
					</div>
				</article>
			{:else}
				<div
					class="spotlight-art mb-5 flex aspect-video items-center justify-center rounded-2xl"
					aria-hidden="true"
				>
					<img
						src="/logo/logo.webp"
						alt=""
						class="size-28 object-contain"
						width="112"
						height="112"
					/>
				</div>
				<Alert.Root role="status"
					><Trophy aria-hidden="true" /><Alert.Title>{m.empty_tournaments()}</Alert.Title
					><Alert.Description>{m.empty_tournaments_note()}</Alert.Description></Alert.Root
				>
			{/if}
		</section>
	</div>

	<section
		class="mt-10 rounded-2xl bg-muted/50 p-6 sm:p-8 lg:mt-12 lg:p-10"
		aria-labelledby="home-start-heading"
	>
		<div class="flex flex-wrap items-center justify-between gap-4">
			<h2 id="home-start-heading" class="text-2xl font-semibold">{m.home_get_started_heading()}</h2>
			<a
				class="inline-flex items-center gap-2 text-sm font-semibold"
				href={resolve(localizeInternalHref('/tournaments'))}
				>{m.action_view_all_tournaments()}<ArrowRight class="size-4" aria-hidden="true" /></a
			>
		</div>
		<ol class="mt-8 grid gap-7 md:grid-cols-3 md:gap-8">
			{#each steps as step, index (step.title)}
				<li class="flex items-start gap-4">
					<span class="font-mono-data pt-1 text-xs text-primary" aria-hidden="true"
						>0{index + 1}</span
					>
					<div>
						<h3 class="font-semibold">{step.title}</h3>
						<p class="mt-2 text-sm leading-6 text-muted-foreground">{step.description}</p>
					</div>
				</li>
			{/each}
		</ol>
	</section>

	<section
		class="flex flex-col items-start gap-5 px-2 pb-2 pt-10 sm:flex-row sm:items-center sm:justify-between sm:pt-12"
		aria-labelledby="home-community-heading"
	>
		<div class="flex items-start gap-4">
			<Gamepad2 class="mt-1 size-6 shrink-0 text-primary" aria-hidden="true" />
			<div>
				<h2 id="home-community-heading" class="text-lg font-semibold">
					{m.home_community_heading()}
				</h2>
				<p class="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
					{m.home_community_description()}
				</p>
			</div>
		</div>
		<Button variant="outline" href="https://facebook.com/hcmusec"
			>{m.home_follow_club()}<ArrowUpRight data-icon="inline-end" aria-hidden="true" /></Button
		>
	</section>
</div>

<style>
	.spotlight-art {
		background-color: color-mix(in srgb, var(--primary) 5%, var(--background));
		background-image: repeating-linear-gradient(
			135deg,
			transparent,
			transparent 22px,
			color-mix(in srgb, var(--primary) 6%, transparent) 22px,
			color-mix(in srgb, var(--primary) 6%, transparent) 23px
		);
	}

	/* The global anchor rule otherwise overrides filled button foregrounds. */
	.home-landing :global(a[data-slot='button'][class*='bg-primary']) {
		color: var(--primary-foreground);
	}
</style>
