<script lang="ts">
	import { resolve } from '$app/paths';
	import type { PublicTournament, PublicTournamentGame, RegistrationState } from '$lib/api/types';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { formatTournamentDateTime } from '$lib/time/tournament-time';
	import { Badge } from '$lib/components/ui/badge';
	import * as Card from '$lib/components/ui/card';

	interface Props {
		tournament: PublicTournament;
		game: PublicTournamentGame;
		displayTimeZone: string;
	}

	let { tournament, game, displayTimeZone }: Props = $props();

	function stateLabel(state: RegistrationState): string {
		switch (state) {
			case 'not_open':
				return m.registration_state_not_open();
			case 'open':
				return m.registration_state_open();
			case 'full':
				return m.registration_state_full();
			case 'closed':
				return m.registration_state_closed();
		}
	}

	function stateClass(state: RegistrationState): string {
		switch (state) {
			case 'open':
					return 'border-success text-success';
			case 'full':
					return 'border-warning text-warning';
			case 'closed':
					return 'border-destructive text-destructive';
			case 'not_open':
					return '';
		}
	}

	function teamSize(): string {
		return game.team_size_min === game.team_size_max
			? String(game.team_size_min)
			: `${game.team_size_min}–${game.team_size_max}`;
	}

	function fee(): string {
		return new Intl.NumberFormat(getLocale(), {
			style: 'currency',
			currency: game.fee_currency,
			currencyDisplay: 'code'
		}).format(Number(game.fee_amount));
	}

	function capacity(): string {
		return game.capacity_remaining === null
			? m.game_capacity_unlimited()
			: String(game.capacity_remaining);
	}
</script>

<article aria-labelledby={`game-${game.id}-title`}>
	<Card.Root class="grid gap-0 py-0 lg:grid-cols-[minmax(12rem,0.8fr)_minmax(0,2fr)_auto]">
		<Card.Header class="p-4 sm:p-5 lg:row-span-2 lg:border-r">
			<Card.Title>
				<h3 id={`game-${game.id}-title`}>{game.game_name}</h3>
			</Card.Title>
			<Card.Description class="font-mono-data text-xs">{game.game_slug}</Card.Description>
			<Card.Action>
				<Badge variant={game.registration_state === 'closed' ? 'destructive' : 'outline'} class={stateClass(game.registration_state)}>
					{stateLabel(game.registration_state)}
				</Badge>
			</Card.Action>
		</Card.Header>

		<Card.Content class="p-0">
			<dl class="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
				<div class="bg-card p-4">
					<dt class="text-xs text-muted-foreground">{m.game_team_size()}</dt>
					<dd class="font-mono-data mt-1 text-sm font-medium">{teamSize()}</dd>
				</div>
				<div class="bg-card p-4 sm:col-span-2">
					<dt class="text-xs text-muted-foreground">{m.game_registration_window()}</dt>
					<dd class="font-mono-data mt-1 text-xs leading-5">
						<time datetime={game.registration_opens_at}>
							{formatTournamentDateTime(game.registration_opens_at, getLocale(), displayTimeZone)}
						</time>
						—
						<time datetime={game.registration_closes_at}>
							{formatTournamentDateTime(game.registration_closes_at, getLocale(), displayTimeZone)}
						</time>
					</dd>
				</div>
				<div class="bg-card p-4">
					<dt class="text-xs text-muted-foreground">{m.game_fee()}</dt>
					<dd class="font-mono-data mt-1 text-xs font-medium">{fee()}</dd>
				</div>
				<div class="bg-card p-4 sm:col-span-4">
					<dt class="text-xs text-muted-foreground">{m.game_capacity()}</dt>
					<dd class="font-mono-data mt-1 text-sm font-medium">{capacity()}</dd>
				</div>
			</dl>
		</Card.Content>

		<Card.Footer class="border-t px-4 py-4 lg:row-span-2 lg:border-l lg:border-t-0">
			{#if game.is_registration_open}
				<a
					class="flex items-center justify-between gap-4 text-sm font-semibold text-primary lg:min-w-36"
					href={resolve(
						localizeInternalHref(`/tournaments/${tournament.slug}/games/${game.id}/register`)
					)}
				>
					{m.action_register()}
					<span class="bracket-node" aria-hidden="true"></span>
				</a>
			{:else}
				<span class="text-sm font-semibold text-muted-foreground">{stateLabel(game.registration_state)}</span>
			{/if}
		</Card.Footer>
	</Card.Root>
</article>
