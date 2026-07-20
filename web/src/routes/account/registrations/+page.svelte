<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { ApiRequestError } from '$lib/api/client';
	import { listRegistrations } from '$lib/api/registrations';
	import type { RegistrationRead, RegistrationStatus } from '$lib/api/types';
	import { replaceInternalLocation } from '$lib/auth/navigation';
	import { clearSession, getAccessToken } from '$lib/auth/session';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { onMount } from 'svelte';

	let registrations = $state<RegistrationRead[]>([]);
	let loading = $state(true);
	let redirecting = $state(false);
	let formErrors = $state<string[]>([]);

	function signInHref(): string {
		const currentHref = `${page.url.pathname}${page.url.search}${page.url.hash}`;
		return `${resolve(localizeInternalHref('/auth/sign-in'))}?redirectTo=${encodeURIComponent(currentHref)}`;
	}

	function redirectToSignIn(clearTokens: boolean): void {
		if (redirecting) return;
		redirecting = true;
		if (clearTokens) clearSession();
		replaceInternalLocation(signInHref());
	}

	function isAuthenticationError(cause: unknown): boolean {
		return cause instanceof ApiRequestError && (cause.status === 401 || cause.status === 403);
	}

	function statusLabel(status: RegistrationStatus): string {
		switch (status) {
			case 'SUBMITTED':
				return m.status_SUBMITTED();
			case 'UNDER_REVIEW':
				return m.status_UNDER_REVIEW();
			case 'APPROVED':
				return m.status_APPROVED();
			case 'REJECTED':
				return m.status_REJECTED();
		}
	}

	function formatDate(value: string): string {
		return new Intl.DateTimeFormat(getLocale(), { dateStyle: 'medium' }).format(new Date(value));
	}

	function formatFee(registration: RegistrationRead): string {
		return new Intl.NumberFormat(getLocale(), {
			style: 'currency',
			currency: registration.fee_currency_snapshot
		}).format(Number(registration.fee_amount_snapshot));
	}

	onMount(async () => {
		const accessToken = getAccessToken();
		if (!accessToken) {
			loading = false;
			redirectToSignIn(false);
			return;
		}

		try {
			registrations = await listRegistrations(accessToken);
		} catch (cause) {
			if (isAuthenticationError(cause)) {
				redirectToSignIn(true);
				return;
			}
			({ formErrors } = formErrorsFrom(cause, m.registrations_load_failed()));
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head>
	<title>{m.registrations_heading()} · {m.app_title()}</title>
	<meta name="description" content={m.registrations_intro()} />
</svelte:head>

<header
	class="grid border border-(--line) lg:grid-cols-[minmax(0,1.55fr)_minmax(15rem,0.45fr)]"
>
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-(--accent)">
			{m.registrations_kicker()}
		</p>
		<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
			{m.registrations_heading()}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-(--text-muted)">
			{m.registrations_intro()}
		</p>
	</div>
	<div
		class="grid content-end border-t border-(--line) bg-(--surface-muted) p-5 lg:border-l lg:border-t-0 lg:p-7"
	>
		<span class="bracket-node" aria-hidden="true"></span>
	</div>
</header>

{#if loading || redirecting}
	<p
		class="mt-8 border border-(--line) bg-(--surface-muted) p-6 text-sm text-(--text-muted)"
		role="status"
	>
		{redirecting ? m.auth_redirecting_to_sign_in() : m.registrations_loading()}
	</p>
{:else if formErrors.length > 0}
	<section class="mt-8"><ErrorSummary errors={formErrors} /></section>
{:else if registrations.length === 0}
	<p
		class="mt-8 border border-(--line) bg-(--surface-muted) p-6 text-sm text-(--text-muted)"
		role="status"
	>
		{m.empty_registrations()}
	</p>
{:else}
	<section class="mt-8 space-y-4" aria-label={m.registrations_heading()}>
		{#each registrations as registration, index (registration.id)}
			<a
				class="group grid border border-(--line) transition-colors hover:border-(--accent) focus-visible:outline focus-visible:outline-offset-2 focus-visible:outline-(--accent) lg:grid-cols-[5rem_minmax(0,1fr)_minmax(13rem,0.42fr)]"
				href={resolve(localizeInternalHref(`/account/registrations/${registration.id}`))}
			>
				<div
					class="grid content-center border-b border-(--line) bg-(--surface-muted) p-4 lg:border-b-0 lg:border-r"
				>
					<span class="font-mono-data text-2xl font-semibold text-(--accent)"
						>{String(index + 1).padStart(2, '0')}</span
					>
				</div>
				<div class="p-5">
					<div class="flex flex-wrap items-center gap-3">
						<span
							class="border border-(--accent) px-2 py-1 text-xs font-semibold text-(--accent)"
							>{statusLabel(registration.status)}</span
						>
						<span class="text-xs text-(--text-muted)"
							>{registration.tournament_game.game_name}</span
						>
					</div>
					<h2 class="font-heading mt-3 text-xl font-semibold group-hover:text-(--accent)">
						{registration.tournament_game.tournament_name}
					</h2>
					{#if registration.team_name}
						<p class="mt-2 text-sm text-(--text-muted)">{registration.team_name}</p>
					{/if}
				</div>
				<dl
					class="grid grid-cols-2 gap-px border-t border-(--line) bg-(--line) text-sm lg:grid-cols-1 lg:border-l lg:border-t-0"
				>
					<div class="bg-white p-4">
						<dt class="text-xs text-(--text-muted)">{m.registration_submitted_label()}</dt>
						<dd class="font-mono-data mt-1 text-xs font-semibold">
							<time datetime={registration.submitted_at}
								>{formatDate(registration.submitted_at)}</time
							>
						</dd>
					</div>
					<div class="bg-white p-4">
						<dt class="text-xs text-(--text-muted)">{m.game_fee()}</dt>
						<dd class="font-mono-data mt-1 text-xs font-semibold">{formatFee(registration)}</dd>
					</div>
				</dl>
			</a>
		{/each}
	</section>
{/if}
