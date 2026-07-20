<script lang="ts">
	import { resolve } from '$app/paths';
	import type { PublicTournament, PublicTournamentGame, RegistrationState } from '$lib/api/types';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { formatTournamentDateTime } from '$lib/time/tournament-time';

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
				return 'text-(--success) border-(--success)';
			case 'full':
				return 'text-(--warning) border-(--warning)';
			case 'closed':
				return 'text-(--error) border-(--error)';
			case 'not_open':
				return 'text-(--text-muted) border-(--line)';
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

<article
	class="grid border border-(--line) bg-white lg:grid-cols-[minmax(12rem,0.8fr)_minmax(0,2fr)_auto]"
	aria-labelledby={`game-${game.id}-title`}
>
	<header
		class="flex items-start justify-between gap-4 p-4 sm:p-5 lg:border-r lg:border-(--line)"
	>
		<div>
			<h3 class="font-heading text-xl font-semibold" id={`game-${game.id}-title`}>
				{game.game_name}
			</h3>
			<p class="font-mono-data mt-1 text-xs text-(--text-muted)">{game.game_slug}</p>
		</div>
		<span class={`border px-2 py-1 text-xs font-semibold ${stateClass(game.registration_state)}`}>
			{stateLabel(game.registration_state)}
		</span>
	</header>

	<dl
		class="grid grid-cols-2 gap-px border-t border-(--line) bg-(--line) sm:grid-cols-4 lg:border-t-0"
	>
		<div class="bg-white p-4">
			<dt class="text-xs text-(--text-muted)">{m.game_team_size()}</dt>
			<dd class="font-mono-data mt-1 text-sm font-medium">{teamSize()}</dd>
		</div>
		<div class="bg-white p-4 sm:col-span-2">
			<dt class="text-xs text-(--text-muted)">{m.game_registration_window()}</dt>
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
		<div class="bg-white p-4">
			<dt class="text-xs text-(--text-muted)">{m.game_fee()}</dt>
			<dd class="font-mono-data mt-1 text-xs font-medium">{fee()}</dd>
		</div>
		<div class="bg-white p-4 sm:col-span-4">
			<dt class="text-xs text-(--text-muted)">{m.game_capacity()}</dt>
			<dd class="font-mono-data mt-1 text-sm font-medium">{capacity()}</dd>
		</div>
	</dl>

	<div class="flex items-center border-t border-(--line) px-4 py-4 lg:border-l lg:border-t-0">
		{#if game.is_registration_open}
			<a
				class="flex w-full items-center justify-between gap-4 text-sm font-semibold text-(--accent) lg:min-w-36"
				href={resolve(
					localizeInternalHref(`/tournaments/${tournament.slug}/games/${game.id}/register`)
				)}
			>
				{m.action_register()}
				<span class="bracket-node" aria-hidden="true"></span>
			</a>
		{:else}
			<span class="text-sm font-semibold text-(--text-muted)">
				{stateLabel(game.registration_state)}
			</span>
		{/if}
	</div>
</article>
