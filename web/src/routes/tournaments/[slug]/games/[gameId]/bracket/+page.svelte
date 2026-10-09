<script lang="ts">
	import { resolve } from '$app/paths';
	import { SvelteMap } from 'svelte/reactivity';
	import { onMount } from 'svelte';
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
	import { Button } from '$lib/components/ui/button';
	import * as Field from '$lib/components/ui/field';
	import * as Alert from '$lib/components/ui/alert';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { formatTournamentDateTime } from '$lib/time/tournament-time';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let stageId = $state<number | undefined>();
	const selectedStage = $derived.by(() => {
		if (data.state !== 'ready') return null;
		const sorted = [...data.competition.stages].sort((a, b) => b.sequence - a.sequence);
		return (
			data.competition.stages.find((stage) => stage.id === (stageId ?? data.selectedStageId)) ??
			sorted.find((stage) => stage.draw_state === 'PUBLISHED') ??
			sorted[0]
		);
	});
	$effect(() => {
		stageId = data.state === 'ready' ? data.selectedStageId : undefined;
		groupId = '';
		roundId = '';
	});
	let groupId = $state('');
	let roundId = $state('');
	let hydrated = $state(false);
	onMount(() => {
		hydrated = true;
	});
	const doubleSections = ['UPPER', 'LOWER', 'FINALS'] as const;

	const tournamentHref = $derived(resolve(localizeInternalHref(`/tournaments/${data.slug}`)));
	const bracketHref = $derived(
		resolve(
			localizeInternalHref(
				`/tournaments/${data.slug}/games/${data.gameId}/bracket${selectedStage ? `?stage=${selectedStage.id}` : ''}`
			)
		)
	);
	const matchLabels = $derived.by(() => {
		const labels = new SvelteMap<number, { code: string; round: string }>();
		if (data.state !== 'ready') return labels;
		for (const stage of data.competition.stages) {
			const isDouble = stage.format === 'DOUBLE_ELIMINATION';
			const rounds = isDouble
				? doubleSections.flatMap((section) =>
						stage.rounds.filter((round) => round.section === section)
					)
				: stage.rounds;
			for (const round of rounds) {
				const roundName =
					stage.format === 'SINGLE_ELIMINATION' && round === rounds.at(-1)
						? m.bracket_final_round()
						: roundLabel(round);
				const context =
					isDouble && round.section !== 'FINALS'
						? `${sectionLabel(round.section)} ${roundName}`
						: roundName;
				for (const match of round.matches) {
					labels.set(match.id, {
						code: match.code,
						round: data.competition.stages.length > 1 ? `${stage.name} · ${context}` : context
					});
				}
			}
		}
		return labels;
	});

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

	function slotLabel(slot: PublicCompetitionMatchSlot): string {
		if (!slot.is_resolved) {
			const code = slot.source_match_id ? matchLabels.get(slot.source_match_id)?.code : null;
			if (code && slot.source_outcome === 'WINNER') return m.bracket_source_winner({ code });
			if (code && slot.source_outcome === 'LOSER') return m.bracket_source_loser({ code });
			return m.bracket_tbd();
		}
		if (slot.is_empty || !slot.entry) return m.bracket_bye();
		return slot.entry.display_tag
			? `${slot.entry.display_name} (${slot.entry.display_tag})`
			: slot.entry.display_name;
	}

	function score(match: PublicCompetitionMatch, slot: PublicCompetitionMatchSlot): string {
		if (match.outcome === 'FORFEIT') return isWinner(match, slot) ? 'W' : 'FF';
		const value = slot.position === 1 ? match.side_one_score : match.side_two_score;
		return value === null ? '—' : String(value);
	}

	function isWinner(match: PublicCompetitionMatch, slot: PublicCompetitionMatchSlot): boolean {
		return Boolean(match.winner && slot.entry?.id === match.winner.id);
	}

	function changeLabel(change: PublicCompetitionChange): string {
		const label = change.match_id === undefined ? undefined : matchLabels.get(change.match_id);
		const code = label ? `${label.code} (${label.round})` : (change.match_code ?? '');
		switch (change.kind) {
			case 'qualification_tie_confirmed':
			case 'group_tie_confirmed':
				return m.bracket_tie_confirmed_change({ group: change.group_name ?? '' });
			case 'draw_published':
				return m.bracket_change_draw_published();
			case 'match_scheduled':
				return m.bracket_change_match_scheduled({ code });
			case 'round_series_length_changed':
				return m.bracket_change_round_series();
			case 'match_series_length_changed':
				return m.bracket_change_match_series({ code });
			case 'match_started':
				return m.bracket_change_match_started({ code });
			case 'match_progress_saved':
				return m.bracket_change_score({ code });
			case 'match_finalized':
				return m.bracket_change_match_finalized({ code });
			case 'result_corrected':
				return m.bracket_change_result_corrected({ code });
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
				outcome:
					snapshot.outcome === 'PLAYED' && snapshot.applied_series_mode === 'FIXED_GAMES'
						? m.bracket_draw()
						: snapshot.outcome
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

	function qualificationLabel(value: string): string {
		switch (value) {
			case 'PROVISIONAL':
				return m.bracket_provisional();
			case 'TIED':
				return m.bracket_tied();
			case 'QUALIFIED':
				return m.bracket_qualified();
			case 'NOT_QUALIFIED':
				return m.bracket_not_qualified();
			case 'RESOLVED':
			case 'CONFIRMED':
				return m.bracket_qualification_resolved();
			case 'SUPERSEDED':
				return m.bracket_historical();
			default:
				return m.bracket_awaiting_qualification();
		}
	}

	function ruleLabel(rule: string): string {
		switch (rule) {
			case 'HEAD_TO_HEAD':
				return m.bracket_head_to_head();
			case 'MATCH_WINS':
				return m.bracket_match_wins();
			case 'GAME_DIFFERENCE':
				return m.bracket_game_difference();
			case 'GAMES_WON':
				return m.bracket_games_won();
			default:
				return rule;
		}
	}
	function entryNames(ids: number[]): string {
		if (data.state !== 'ready') return '';
		return (
			ids
				.map(
					(id) =>
						data.competition.stages
							.flatMap((stage) => stage.entries)
							.find((entry) => entry.id === id)?.display_name ?? ''
				)
				.filter(Boolean)
				.join(', ') || m.bracket_awaiting_qualification()
		);
	}
</script>

<svelte:head>
	<title>{m.bracket_title()} · {m.app_title()}</title>
	<meta name="description" content={m.bracket_meta_description()} />
</svelte:head>

{#snippet matchCard(match: PublicCompetitionMatch)}
	{@const code = matchLabels.get(match.id)?.code ?? match.code}
	<li class="bracket-match relative">
		<article
			class:border-primary={match.status === 'LIVE'}
			class="rounded-xl border bg-card shadow-xs"
			aria-labelledby={`match-${match.id}-code`}
		>
			<header class="flex items-center justify-between gap-3 border-b px-3 py-2">
				<h3 id={`match-${match.id}-code`} class="font-mono-data text-xs font-semibold">
					{code}
				</h3>
				<div class="flex items-center gap-2">
					{#if match.historical}<Badge variant="outline">{m.bracket_historical()}</Badge>{/if}
					<Badge variant={match.status === 'LIVE' ? 'default' : 'outline'}>
						{matchStatusLabel(match.status)}
					</Badge>
				</div>
			</header>
			<ul class="divide-y" aria-label={m.bracket_match_entrants({ code })}>
				{#each match.slots as slot (slot.position)}
					<li
						class:font-semibold={isWinner(match, slot)}
						class="grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-3 px-3 py-2 text-sm"
					>
						<span class="truncate">
							{slotLabel(slot)}
							{#if isWinner(match, slot)}
								<span class="sr-only"> · {m.bracket_winner()}</span>
							{/if}
						</span>
						<span class="font-mono-data text-right">{score(match, slot)}</span>
					</li>
				{/each}
			</ul>
			<footer
				class="flex flex-wrap justify-between gap-2 border-t px-3 py-2 text-xs text-muted-foreground"
			>
				<span
					>{match.effective_series_mode === 'FIXED_GAMES'
						? m.bracket_fixed_games({ count: match.effective_series_length })
						: m.bracket_best_of({ count: match.effective_series_length })}</span
				>
				{#if match.status === 'FINAL' && match.outcome === 'PLAYED' && !match.winner && match.effective_series_mode === 'FIXED_GAMES'}<Badge
						variant="secondary">{m.bracket_draw()}</Badge
					>{/if}
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

<main class="mx-auto flex min-w-0 max-w-7xl flex-col gap-8">
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
		{@const stage = selectedStage ?? data.competition.stages[0]}
		<header class="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
			<div>
				<p class="text-sm font-medium text-muted-foreground">{data.competition.tournament_name}</p>
				<h1 class="font-heading mt-1 text-3xl font-semibold sm:text-5xl">
					{data.competition.game_name} · {m.bracket_title()}
				</h1>
				<p class="mt-2 text-muted-foreground">{stage.name}</p>
			</div>
			<div class="flex items-center gap-3">
				<Badge variant="outline" class="w-fit">{stageStatusLabel(stage.status)}</Badge><Button
					variant="outline"
					href={bracketHref}>{m.bracket_refresh()}</Button
				>
			</div>
		</header>

		<Field.FieldGroup
			><Field.Field>
				<Field.FieldLabel for="stage-select">{m.bracket_stage_selection()}</Field.FieldLabel>
				<select
					id="stage-select"
					disabled={!hydrated}
					value={String(stage.id)}
					class="h-10 rounded-md border bg-background px-3"
					onchange={(event) => {
						stageId = Number(event.currentTarget.value);
						groupId = '';
						roundId = '';
					}}
				>
					{#each data.competition.stages as item (item.id)}<option value={String(item.id)}
							>{item.sequence}. {item.name}</option
						>{/each}
				</select>
			</Field.Field></Field.FieldGroup
		>
		{#if stage.draw_state === 'AWAITING_REPLACEMENT'}<Alert.Root
				><Alert.Title>{m.bracket_awaiting_replacement()}</Alert.Title><Alert.Description
					>{m.bracket_replacement_help()}</Alert.Description
				></Alert.Root
			>{/if}
		{#if stage.qualification && stage.format !== 'ROUND_ROBIN'}
			{@const qualification = stage.qualification}
			<section class="flex flex-col gap-4" aria-labelledby="qualification-heading">
				<h2 id="qualification-heading" class="font-heading text-2xl font-semibold">
					{m.bracket_top_n({ count: qualification.advance_count ?? 0 })}
				</h2>
				<Badge variant="outline" class="w-fit">{qualificationLabel(qualification.state)}</Badge>
				{#if qualification.block_reason}<Alert.Root
						><Alert.Title>{m.bracket_awaiting_qualification()}</Alert.Title><Alert.Description
							>{qualification.block_reason}</Alert.Description
						></Alert.Root
					>{/if}
				{#if qualification.qualifiers.length}<p>
						{m.bracket_qualifiers({
							names: qualification.qualifiers.map((entry) => entry.display_name).join(', ')
						})}
					</p>{/if}
				{#if qualification.placement_bands.length}<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead
								><tr
									><th scope="col" class="px-4 py-3 text-left">{m.bracket_placement()}</th><th
										scope="col"
										class="px-4 py-3 text-left">{m.bracket_entrant()}</th
									></tr
								></thead
							><tbody
								>{#each qualification.placement_bands as band, index (band[0].id)}<tr class="border-t"
										><th scope="row" class="px-4 py-3 text-left"
											>{qualification.placement_bands
												.slice(0, index)
												.reduce((count, prior) => count + prior.length, 1)}</th
										><td class="px-4 py-3">{band.map((entry) => entry.display_name).join(', ')}</td
										></tr
									>{/each}</tbody
							>
						</table>
					</div>{/if}
				{#each qualification.cutoff_ties as tie, index (tie.resolution_id ?? `pending-${index}`)}<Alert.Root
						><Alert.Title
							>{tie.method === 'MANUAL'
								? m.bracket_organizer_decision()
								: tie.method === 'EXTRA_MATCHES'
									? m.bracket_extra_contests()
									: m.bracket_awaiting_qualification()}</Alert.Title
						><Alert.Description
							>{tie.tied_entries.map((entry) => entry.display_name).join(', ')} · {m.bracket_qualifying_places(
								{ count: tie.places }
							)} · {qualificationLabel(tie.state)}</Alert.Description
						></Alert.Root
					>{/each}
			</section>
		{/if}
		{#if stage.format !== 'ROUND_ROBIN' && (stage.champion || stage.completed_without_champion)}
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

		{#if stage.format === 'ROUND_ROBIN' && stage.round_robin_rules}
			{@const rules = stage.round_robin_rules}
			{@const group = stage.groups.find((g) => String(g.id) === groupId) ?? stage.groups[0]}
			{@const groupRounds = stage.rounds.filter((r) => r.group_id === group?.id)}
			{@const selectedRound = groupRounds.find((r) => String(r.id) === roundId) ?? groupRounds[0]}
			<section aria-labelledby="group-rules-heading" class="flex flex-col gap-3">
				<h2 id="group-rules-heading" class="font-heading text-2xl font-semibold">
					{m.bracket_rules()}
				</h2>
				<p>
					{m.bracket_meetings({ count: rules.meetings })} · {m.bracket_match_points({
						win: rules.win_points,
						draw: rules.draw_points,
						loss: rules.loss_points
					})}
				</p>
				<p>
					{rules.tiebreaks.length
						? rules.tiebreaks.map(ruleLabel).join(' → ')
						: m.bracket_no_tiebreaks()}
				</p>
				<p class="text-sm text-muted-foreground">{m.bracket_rules_help()}</p>
			</section>
			{#if stage.status === 'COMPLETE'}<Alert.Root
					><Alert.Title>{m.bracket_group_complete()}</Alert.Title><Alert.Description
						>{m.bracket_qualification_resolved()}</Alert.Description
					></Alert.Root
				>{/if}
			<Field.FieldGroup
				><Field.Field
					><Field.FieldLabel for="group-select">{m.bracket_group()}</Field.FieldLabel>
					<select
						id="group-select"
						disabled={!hydrated}
						value={String(group?.id ?? '')}
						onchange={(event) => {
							groupId = event.currentTarget.value;
							roundId = '';
						}}
						class="w-full rounded-md border bg-background px-3 py-2 sm:max-w-sm"
						aria-label={m.bracket_group()}
					>
						{#each stage.groups as item (item.id)}<option value={String(item.id)}
								>{item.name} · {m.bracket_entries({ count: item.entries.length })}</option
							>{/each}
					</select>
				</Field.Field></Field.FieldGroup
			>
			{#if group}
				<section class="flex min-w-0 flex-col gap-4" aria-labelledby="group-standings-heading">
					<h2 id="group-standings-heading" class="font-heading text-2xl font-semibold">
						{group.name} · {m.bracket_standings()}
					</h2>
					<div class="flex flex-wrap gap-3">
						<Badge variant="outline">{qualificationLabel(group.qualification_state)}</Badge><span
							>{m.bracket_qualifying_places({ count: group.qualifying_places })}</span
						>
					</div>
					<p class="text-sm text-muted-foreground">{m.bracket_provisional_help()}</p>
					<!-- svelte-ignore a11y_no_noninteractive_tabindex (keyboard access to a wide standings table) -->
					<div
						class="max-w-full overflow-x-auto rounded-xl border"
						role="region"
						aria-label={m.bracket_standings()}
						tabindex="0"
					>
						<table class="w-full text-left text-sm whitespace-nowrap">
							<caption class="sr-only">{group.name} · {m.bracket_standings()}</caption>
							<thead class="border-b bg-muted/30"
								><tr
									>{#each [m.bracket_rank(), m.bracket_entrant(), m.bracket_played(), m.bracket_wins(), m.bracket_draws(), m.bracket_losses(), m.bracket_points(), m.bracket_games_won(), m.bracket_game_difference(), m.bracket_qualification()] as label (label)}<th
											scope="col"
											class="px-4 py-3">{label}</th
										>{/each}</tr
								></thead
							>
							<tbody
								>{#each group.standings as row (row.entry.id)}<tr class="border-b last:border-0"
										><td class="px-4 py-3 font-mono-data">{row.rank}</td><th
											scope="row"
											class="px-4 py-3">{row.entry.display_name}</th
										><td class="px-4 py-3">{row.played}</td><td class="px-4 py-3">{row.wins}</td><td
											class="px-4 py-3">{row.draws}</td
										><td class="px-4 py-3">{row.losses}</td><td class="px-4 py-3 font-mono-data"
											>{row.points}</td
										><td class="px-4 py-3">{row.games_won}</td><td class="px-4 py-3"
											>{row.game_difference}</td
										><td class="px-4 py-3"
											><Badge variant="outline">{qualificationLabel(row.qualification)}</Badge></td
										></tr
									>{/each}</tbody
							>
						</table>
					</div>
					{#if group.qualifiers.length}<p>
							{m.bracket_qualifiers({
								names: group.qualifiers.map((entry) => entry.display_name).join(', ')
							})}
						</p>{/if}
					{#if group.tie_resolutions.length}<p class="text-sm text-muted-foreground">
							{m.bracket_extra_rules()}
						</p>
						<h3 class="font-semibold">{m.bracket_tie_history()}</h3>
						<ul class="flex flex-col gap-3">
							{#each group.tie_resolutions as tie (tie.id)}<li>
									<Badge variant="outline"
										>{tie.method === 'MANUAL'
											? m.bracket_organizer_decision()
											: m.bracket_extra_contests()}</Badge
									> · {qualificationLabel(tie.state)}
									<p class="text-sm text-muted-foreground">
										{tie.tied_entries.map((e) => e.display_name).join(', ')}
									</p>
									{#if tie.ordered_entries.length}<p>
											{tie.ordered_entries.map((e) => e.display_name).join(' → ')}
										</p>{/if}
								</li>{/each}
						</ul>{/if}
				</section>
				<section class="flex flex-col gap-6" aria-labelledby="group-rounds-heading">
					<h2 id="group-rounds-heading" class="font-heading text-2xl font-semibold">
						{m.bracket_rounds()}
					</h2>
					<Field.Field
						><Field.FieldLabel for="round-select">{m.bracket_round_selection()}</Field.FieldLabel>
						<select
							id="round-select"
							aria-label={m.bracket_round_selection()}
							disabled={!hydrated}
							value={String(selectedRound?.id ?? '')}
							onchange={(event) => {
								roundId = event.currentTarget.value;
							}}
							class="w-full rounded-md border bg-background px-3 py-2 sm:max-w-sm"
						>
							{#each groupRounds as item (item.id)}<option value={String(item.id)}
									>{item.section === 'TIEBREAK'
										? m.bracket_extra_contests() + ' · '
										: ''}{roundLabel(item)}{item.matches.some((match) => match.historical)
										? ' · ' + m.bracket_historical()
										: ''}</option
								>{/each}
						</select></Field.Field
					>
					{#if selectedRound}{@const round = selectedRound}
						<section class="flex flex-col gap-3">
							<h3 class="font-semibold">
								{round.section === 'TIEBREAK' ? m.bracket_extra_contests() + ' · ' : ''}{roundLabel(
									round
								)}
							</h3>
							{#if round.resting_entry}<p class="text-sm text-muted-foreground">
									{m.bracket_rest({ name: round.resting_entry.display_name })}
								</p>{/if}
							<ol class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
								{#each round.matches as match (match.id)}{@render matchCard(match)}{/each}
							</ol>
						</section>{/if}
				</section>
			{/if}
		{:else}
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
														{@render matchCard(match)}
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
													{@render matchCard(match)}
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
											{@render matchCard(match)}
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
										{@render matchCard(match)}
									{/each}
								</ol>
							</section>
						{/each}
					</div>
				{/if}
			</section>
		{/if}

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
												codes: change.reset_matches
													.map((match) => matchLabels.get(match.match_id)?.code ?? match.match_code)
													.join(', ')
											})}
										</p>
									{/if}
									{#each change.reset_matches ?? [] as snapshot (snapshot.match_id)}
										<p>
											{matchLabels.get(snapshot.match_id)?.code ?? snapshot.match_code}: {snapshotSummary(
												snapshot
											)}
										</p>
									{/each}
									{#each change.reset_final_changes ?? [] as reset (reset.match_id)}
										<p>
											{m.bracket_reset_change({
												code: matchLabels.get(reset.match_id)?.code ?? reset.match_code,
												before: activationLabel(reset.before),
												after: activationLabel(reset.after)
											})}
										</p>
									{/each}
								</div>
							{/if}
							{#if change.ordered_entries?.length}<p class="text-sm">
									{change.ordered_entries.join(' → ')}
								</p>{/if}
							{#if change.handoff_impact?.retired_draws.length}<p class="text-sm">
									{m.bracket_retired_draws({ count: change.handoff_impact.retired_draws.length })}
								</p>
								{#each change.handoff_impact.reset_matches as snapshot (snapshot.match_id)}<p
										class="text-xs text-muted-foreground"
									>
										{m.bracket_historical()} · {snapshotSummary(snapshot)}
									</p>{/each}{/if}
							{#if change.group_impact}<p class="text-sm">
									{m.bracket_qualifier_change({
										before: entryNames(change.group_impact.before.qualifiers),
										after: entryNames(change.group_impact.after.qualifiers)
									})}
								</p>
								<p class="text-sm">
									{m.bracket_group_correction({
										group: change.group_impact.group_name,
										before: qualificationLabel(change.group_impact.before.qualification_state),
										after: qualificationLabel(change.group_impact.after.qualification_state)
									})}
								</p>
								<p class="text-sm text-muted-foreground">
									{m.bracket_tie_superseded({
										count: change.group_impact.invalidated_resolution_ids.length
									})}
								</p>
								{#each change.group_impact.historical_matches as snapshot (snapshot.match_id)}<p
										class="text-xs text-muted-foreground"
									>
										{m.bracket_historical()} · {snapshotSummary(snapshot)}
									</p>{/each}{/if}
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
		.bracket-round .bracket-match::after {
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
