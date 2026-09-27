<script lang="ts">
	import { resolve } from '$app/paths';
	import type {
		CompetitionMatchStatus,
		CompetitionStageStatus,
		PublicCompetitionChange,
		PublicCompetitionMatch,
		PublicCompetitionMatchSlot,
		PublicCompetitionMatchSnapshot,
		PublicCompetitionRound
	} from '$lib/api/types';
	import { Badge } from '$lib/components/ui/badge';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { formatTournamentDateTime } from '$lib/time/tournament-time';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const doubleSections = ['UPPER', 'LOWER', 'FINALS'] as const;

	const tournamentHref = $derived(resolve(localizeInternalHref(`/tournaments/${data.slug}`)));
	const bracketHref = $derived(
		resolve(localizeInternalHref(`/tournaments/${data.slug}/games/${data.gameId}/bracket`))
	);

	function stageStatusLabel(status: CompetitionStageStatus): string {
		switch (status) {
			case 'READY':
				return m.bracket_stage_ready();
			case 'IN_PROGRESS':
				return m.bracket_stage_live();
			case 'COMPLETE':
				return m.bracket_stage_complete();
			default:
				return m.bracket_stage_waiting();
		}
	}

	function matchStatusLabel(status: CompetitionMatchStatus): string {
		switch (status) {
			case 'LIVE':
				return m.bracket_match_live();
			case 'FINAL':
				return m.bracket_match_final();
			case 'PENDING':
				return m.bracket_match_pending();
			case 'CONDITIONAL':
				return m.bracket_match_conditional();
			case 'NOT_REQUIRED':
				return m.bracket_match_not_required();
		}
	}

	function slotLabel(slot: PublicCompetitionMatchSlot, matchCodes: Map<number, string>): string {
		if (!slot.is_resolved) {
			const code = slot.source_match_id ? matchCodes.get(slot.source_match_id) : null;
			if (code && slot.source_outcome === 'WINNER') return m.bracket_source_winner({ code });
			if (code && slot.source_outcome === 'LOSER') return m.bracket_source_loser({ code });
			return m.bracket_tbd();
		}
		if (slot.is_empty || !slot.entry) return m.bracket_bye();
		return slot.entry.display_tag
			? `${slot.entry.display_name} (${slot.entry.display_tag})`
			: slot.entry.display_name;
	}

	function score(match: PublicCompetitionMatch, position: 1 | 2): string {
		const value = position === 1 ? match.side_one_score : match.side_two_score;
		return value === null ? '—' : String(value);
	}

	function isWinner(match: PublicCompetitionMatch, slot: PublicCompetitionMatchSlot): boolean {
		return Boolean(match.winner && slot.entry?.id === match.winner.id);
	}

	function changeLabel(change: PublicCompetitionChange): string {
		switch (change.kind) {
			case 'draw_published':
				return m.bracket_change_draw_published();
			case 'match_scheduled':
				return m.bracket_change_match_scheduled({ code: change.match_code ?? '' });
			case 'round_series_length_changed':
				return m.bracket_change_round_series();
			case 'match_series_length_changed':
				return m.bracket_change_match_series({ code: change.match_code ?? '' });
			case 'match_started':
				return m.bracket_change_match_started({ code: change.match_code ?? '' });
			case 'match_progress_saved':
				return m.bracket_change_score({ code: change.match_code ?? '' });
			case 'match_finalized':
				return m.bracket_change_match_finalized({ code: change.match_code ?? '' });
			case 'result_corrected':
				return m.bracket_change_result_corrected({ code: change.match_code ?? '' });
			default:
				return m.bracket_change_updated();
		}
	}

	function sectionLabel(section: string): string {
		switch (section) {
			case 'UPPER':
				return m.bracket_upper();
			case 'LOWER':
				return m.bracket_lower();
			default:
				return m.bracket_finals();
		}
	}

	function roundLabel(round: PublicCompetitionRound): string {
		if (round.section === 'FINALS') {
			return round.number === 2 ? m.bracket_reset_final() : m.bracket_final_round();
		}
		return m.bracket_round({ number: round.number });
	}

	function snapshotSummary(snapshot: PublicCompetitionMatchSnapshot): string {
		if (!snapshot.winner) {
			return m.bracket_change_result_no_winner({
				outcome: snapshot.outcome
					? outcomeLabel(snapshot.outcome)
					: matchStatusLabel(snapshot.status),
				sideOne: snapshot.side_one ?? m.bracket_tbd(),
				sideOneScore: snapshot.side_one_score ?? '—',
				sideTwoScore: snapshot.side_two_score ?? '—',
				sideTwo: snapshot.side_two ?? m.bracket_tbd()
			});
		}
		return m.bracket_change_result_summary({
			outcome: snapshot.outcome
				? outcomeLabel(snapshot.outcome)
				: matchStatusLabel(snapshot.status),
			sideOne: snapshot.side_one ?? m.bracket_tbd(),
			sideOneScore: snapshot.side_one_score ?? '—',
			sideTwoScore: snapshot.side_two_score ?? '—',
			sideTwo: snapshot.side_two ?? m.bracket_tbd(),
			winner: snapshot.winner
		});
	}

	function outcomeLabel(outcome: string): string {
		switch (outcome) {
			case 'PLAYED':
				return m.bracket_outcome_played();
			case 'FORFEIT':
				return m.bracket_outcome_forfeit();
			case 'DOUBLE_FORFEIT':
				return m.bracket_outcome_double_forfeit();
			case 'BYE':
				return m.bracket_outcome_bye();
			case 'EMPTY':
				return m.bracket_outcome_empty();
			default:
				return outcome;
		}
	}

	function activationLabel(value: 'ACTIVE' | 'CONDITIONAL' | 'NOT_REQUIRED'): string {
		switch (value) {
			case 'ACTIVE':
				return m.bracket_reset_active();
			case 'CONDITIONAL':
				return m.bracket_match_conditional();
			case 'NOT_REQUIRED':
				return m.bracket_match_not_required();
		}
	}
</script>

<svelte:head>
	<title>{m.bracket_title()} · {m.app_title()}</title>
	<meta name="description" content={m.bracket_meta_description()} />
</svelte:head>

{#snippet matchCard(match: PublicCompetitionMatch, matchCodes: Map<number, string>)}
	<li class="bracket-match relative">
		<article
			class:border-primary={match.status === 'LIVE'}
			class="rounded-xl border bg-card shadow-xs"
			aria-labelledby={`match-${match.id}-code`}
		>
			<header class="flex items-center justify-between gap-3 border-b px-3 py-2">
				<h3 id={`match-${match.id}-code`} class="font-mono-data text-xs font-semibold">
					{match.code}
				</h3>
				<div class="flex items-center gap-2">
					{#if match.historical}<Badge variant="outline">{m.bracket_historical()}</Badge>{/if}
					<Badge variant={match.status === 'LIVE' ? 'default' : 'outline'}>
						{matchStatusLabel(match.status)}
					</Badge>
				</div>
			</header>
			<ul class="divide-y" aria-label={m.bracket_match_entrants({ code: match.code })}>
				{#each match.slots as slot (slot.position)}
					<li
						class:font-semibold={isWinner(match, slot)}
						class="grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-3 px-3 py-2 text-sm"
					>
						<span class="truncate">
							{slotLabel(slot, matchCodes)}
							{#if isWinner(match, slot)}
								<span class="sr-only"> · {m.bracket_winner()}</span>
							{/if}
						</span>
						<span class="font-mono-data text-right">{score(match, slot.position)}</span>
					</li>
				{/each}
			</ul>
			<footer
				class="flex flex-wrap justify-between gap-2 border-t px-3 py-2 text-xs text-muted-foreground"
			>
				<span>{m.bracket_best_of({ count: match.effective_series_length })}</span>
				{#if match.scheduled_at}
					<time datetime={match.scheduled_at}>
						{formatTournamentDateTime(match.scheduled_at, getLocale(), data.displayTimeZone)}
					</time>
				{:else}
					<span>{m.bracket_schedule_tba()}</span>
				{/if}
			</footer>
		</article>
	</li>
{/snippet}

<main class="mx-auto flex max-w-7xl flex-col gap-8">
	<a
		class="w-fit text-sm font-medium text-primary underline underline-offset-4"
		href={tournamentHref}
	>
		{m.bracket_back_to_tournament()}
	</a>

	{#if data.state === 'unavailable'}
		<section class="rounded-xl border bg-muted/30 p-6" role="status">
			<h1 class="font-heading text-3xl font-semibold">{m.bracket_title()}</h1>
			<p class="mt-3 max-w-2xl text-muted-foreground">{m.bracket_unavailable()}</p>
		</section>
	{:else if data.state === 'refresh'}
		<section class="rounded-xl border bg-muted/30 p-6" role="status">
			<h1 class="font-heading text-3xl font-semibold">{m.bracket_title()}</h1>
			<p class="mt-3 max-w-2xl text-muted-foreground">{m.bracket_refresh_required()}</p>
			<a
				class="mt-4 inline-flex font-semibold text-primary underline underline-offset-4"
				href={bracketHref}
			>
				{m.bracket_refresh()}
			</a>
		</section>
	{:else}
		{@const stage = data.competition.stages[0]}
		{@const matchCodes = new Map(
			stage.rounds.flatMap((round) => round.matches.map((match) => [match.id, match.code]))
		)}
		<header class="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
			<div>
				<p class="text-sm font-medium text-muted-foreground">{data.competition.tournament_name}</p>
				<h1 class="font-heading mt-1 text-3xl font-semibold sm:text-5xl">
					{data.competition.game_name} · {m.bracket_title()}
				</h1>
				<p class="mt-2 text-muted-foreground">{stage.name}</p>
			</div>
			<Badge variant="outline" class="w-fit">{stageStatusLabel(stage.status)}</Badge>
		</header>

		{#if stage.champion || stage.completed_without_champion}
			<section
				class="rounded-xl border border-primary/40 bg-primary/5 p-5"
				aria-labelledby="champion-heading"
			>
				<h2 id="champion-heading" class="text-sm font-semibold text-primary">
					{m.bracket_champion()}
				</h2>
				<p class="font-heading mt-2 text-2xl font-semibold">
					{stage.champion?.display_name ?? m.bracket_no_champion()}
				</p>
			</section>
		{/if}

		<section aria-labelledby="bracket-rounds-heading">
			<div class="mb-4 flex items-end justify-between gap-4">
				<h2 id="bracket-rounds-heading" class="font-heading text-2xl font-semibold">
					{m.bracket_rounds()}
				</h2>
				<p class="text-sm text-muted-foreground">
					{m.bracket_entries({ count: stage.entries.length })}
				</p>
			</div>

			{#if stage.format === 'DOUBLE_ELIMINATION'}
				<p class="mb-6 text-sm text-muted-foreground">
					{stage.grand_final_policy === 'RESET'
						? m.bracket_reset_policy()
						: m.bracket_no_reset_policy()}
				</p>
				{#each doubleSections as section (section)}
					{@const rounds = stage.rounds.filter((round) => round.section === section)}
					{#if rounds.length}
						<section class="mb-8" aria-labelledby={`section-${section.toLowerCase()}`}>
							<h3
								id={`section-${section.toLowerCase()}`}
								class="font-heading mb-4 text-xl font-semibold"
							>
								{sectionLabel(section)}
							</h3>
							<!-- svelte-ignore a11y_no_noninteractive_tabindex (scrolling bracket needs keyboard focus) -->
							<div
								class="desktop-bracket hidden overflow-x-auto pb-4 md:block"
								role="region"
								aria-label={sectionLabel(section)}
								tabindex="0"
							>
								<div class="grid min-w-max grid-flow-col auto-cols-[18rem] gap-10 pr-8">
									{#each rounds as round (round.id)}
										<section class="bracket-round flex min-h-[28rem] flex-col">
											<h4 class="mb-4 text-center font-semibold">{roundLabel(round)}</h4>
											<ol class="flex flex-1 flex-col justify-around gap-6">
												{#each round.matches as match (match.id)}
													{@render matchCard(match, matchCodes)}
												{/each}
											</ol>
										</section>
									{/each}
								</div>
							</div>
							<div class="mobile-bracket flex flex-col gap-8 md:hidden">
								{#each rounds as round (round.id)}
									<section>
										<h4 class="mb-3 font-semibold">{roundLabel(round)}</h4>
										<ol class="flex flex-col gap-4">
											{#each round.matches as match (match.id)}
												{@render matchCard(match, matchCodes)}
											{/each}
										</ol>
									</section>
								{/each}
							</div>
						</section>
					{/if}
				{/each}
			{:else}
				<!-- svelte-ignore a11y_no_noninteractive_tabindex (scrolling bracket needs keyboard focus) -->
				<div
					class="desktop-bracket hidden overflow-x-auto pb-4 md:block"
					role="region"
					aria-label={m.bracket_rounds()}
					tabindex="0"
				>
					<div class="grid min-w-max grid-flow-col auto-cols-[18rem] gap-10 pr-8">
						{#each stage.rounds as round, index (round.id)}
							<section
								class="bracket-round flex min-h-[28rem] flex-col"
								aria-labelledby={`round-${round.id}-desktop`}
							>
								<h3 id={`round-${round.id}-desktop`} class="mb-4 text-center font-semibold">
									{index === stage.rounds.length - 1
										? m.bracket_final_round()
										: m.bracket_round({ number: round.number })}
								</h3>
								<ol class="flex flex-1 flex-col justify-around gap-6">
									{#each round.matches as match (match.id)}
										{@render matchCard(match, matchCodes)}
									{/each}
								</ol>
							</section>
						{/each}
					</div>
				</div>

				<div class="mobile-bracket flex flex-col gap-8 md:hidden">
					{#each stage.rounds as round, index (round.id)}
						<section aria-labelledby={`round-${round.id}-mobile`}>
							<h3 id={`round-${round.id}-mobile`} class="mb-3 font-semibold">
								{index === stage.rounds.length - 1
									? m.bracket_final_round()
									: m.bracket_round({ number: round.number })}
							</h3>
							<ol class="flex flex-col gap-4">
								{#each round.matches as match (match.id)}
									{@render matchCard(match, matchCodes)}
								{/each}
							</ol>
						</section>
					{/each}
				</div>
			{/if}
		</section>

		<section class="border-t pt-6" aria-labelledby="bracket-changes-heading">
			<h2 id="bracket-changes-heading" class="font-heading text-2xl font-semibold">
				{m.bracket_changes()}
			</h2>
			{#if data.changes.results.length}
				<ol class="mt-4 divide-y rounded-xl border">
					{#each data.changes.results as change (change.revision)}
						<li class="flex flex-col gap-2 px-4 py-3">
							<div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
								<span class="text-sm">{changeLabel(change)}</span>
								<time
									class="font-mono-data text-xs text-muted-foreground"
									datetime={change.created_at}
								>
									{formatTournamentDateTime(change.created_at, getLocale(), data.displayTimeZone)}
								</time>
							</div>
							{#if change.kind === 'result_corrected'}
								<div class="space-y-1 text-xs text-muted-foreground">
									{#if change.before}
										<p>{m.bracket_change_before({ summary: snapshotSummary(change.before) })}</p>
									{/if}
									{#if change.after}
										<p>{m.bracket_change_after({ summary: snapshotSummary(change.after) })}</p>
									{/if}
									{#if change.reset_matches?.length}
										<p>
											{m.bracket_change_affected({
												codes: change.reset_matches.map((match) => match.match_code).join(', ')
											})}
										</p>
									{/if}
									{#each change.reset_matches ?? [] as snapshot (snapshot.match_id)}
										<p>{snapshot.match_code}: {snapshotSummary(snapshot)}</p>
									{/each}
									{#each change.reset_final_changes ?? [] as reset (reset.match_id)}
										<p>
											{m.bracket_reset_change({
												code: reset.match_code,
												before: activationLabel(reset.before),
												after: activationLabel(reset.after)
											})}
										</p>
									{/each}
								</div>
							{/if}
						</li>
					{/each}
				</ol>
			{:else}
				<p class="mt-3 text-sm text-muted-foreground">{m.bracket_changes_empty()}</p>
			{/if}
		</section>
	{/if}
</main>

<style>
	@media (min-width: 768px) {
		.bracket-match::after {
			position: absolute;
			top: 50%;
			left: 100%;
			width: 2.5rem;
			border-top: 1px solid var(--border);
			content: '';
		}

		.bracket-round:last-child .bracket-match::after {
			display: none;
		}
	}
</style>
