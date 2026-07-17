<script lang="ts">
	import type { Pathname } from '$app/types';
	import { resolve } from '$app/paths';
	import type { PublicTournament, PublicTournamentGame, RegistrationState } from '$lib/api/types';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';

	interface Props {
		tournament: PublicTournament;
		game: PublicTournamentGame;
	}

	let { tournament, game }: Props = $props();

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
				return 'text-[var(--success)] border-[var(--success)]';
			case 'full':
				return 'text-[var(--warning)] border-[var(--warning)]';
			case 'closed':
				return 'text-[var(--error)] border-[var(--error)]';
			case 'not_open':
				return 'text-[var(--text-muted)] border-[var(--line)]';
		}
	}

	function formatDate(value: string): string {
		return new Intl.DateTimeFormat(getLocale(), {
			dateStyle: 'medium',
			timeStyle: 'short'
		}).format(new Date(value));
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
	class="grid border border-[var(--line)] bg-white lg:grid-cols-[minmax(12rem,0.8fr)_minmax(0,2fr)_auto]"
	aria-labelledby={`game-${game.id}-title`}
>
	<header
		class="flex items-start justify-between gap-4 p-4 sm:p-5 lg:border-r lg:border-[var(--line)]"
	>
		<div>
			<h3 class="font-heading text-xl font-semibold" id={`game-${game.id}-title`}>
				{game.game_name}
			</h3>
			<p class="font-mono-data mt-1 text-xs text-[var(--text-muted)]">{game.game_slug}</p>
		</div>
		<span class={`border px-2 py-1 text-xs font-semibold ${stateClass(game.registration_state)}`}>
			{stateLabel(game.registration_state)}
		</span>
	</header>

	<dl
		class="grid grid-cols-2 gap-px border-t border-[var(--line)] bg-[var(--line)] sm:grid-cols-4 lg:border-t-0"
	>
		<div class="bg-white p-4">
			<dt class="text-xs text-[var(--text-muted)]">{m.game_team_size()}</dt>
			<dd class="font-mono-data mt-1 text-sm font-medium">{teamSize()}</dd>
		</div>
		<div class="bg-white p-4 sm:col-span-2">
			<dt class="text-xs text-[var(--text-muted)]">{m.game_registration_window()}</dt>
			<dd class="font-mono-data mt-1 text-xs leading-5">
				{formatDate(game.registration_opens_at)} — {formatDate(game.registration_closes_at)}
			</dd>
		</div>
		<div class="bg-white p-4">
			<dt class="text-xs text-[var(--text-muted)]">{m.game_fee()}</dt>
			<dd class="font-mono-data mt-1 text-xs font-medium">{fee()}</dd>
		</div>
		<div class="bg-white p-4 sm:col-span-4">
			<dt class="text-xs text-[var(--text-muted)]">{m.game_capacity()}</dt>
			<dd class="font-mono-data mt-1 text-sm font-medium">{capacity()}</dd>
		</div>
	</dl>

	<div class="flex items-center border-t border-[var(--line)] px-4 py-4 lg:border-l lg:border-t-0">
		{#if game.is_registration_open}
			<a
				class="flex w-full items-center justify-between gap-4 text-sm font-semibold text-[var(--accent)] lg:min-w-36"
				href={resolve(
					`/tournaments/${tournament.slug}/games/${game.game_slug}/register` as Pathname
				)}
			>
				{m.action_register()}
				<span class="bracket-node" aria-hidden="true"></span>
			</a>
		{:else}
			<span class="text-sm font-semibold text-[var(--text-muted)]">
				{stateLabel(game.registration_state)}
			</span>
		{/if}
	</div>
</article>
