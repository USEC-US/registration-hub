<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { ApiRequestError } from '$lib/api/client';
	import { getRegistration } from '$lib/api/registrations';
	import type { RegistrationRead, RegistrationStatus } from '$lib/api/types';
	import { replaceInternalLocation } from '$lib/auth/navigation';
	import { clearSession, getAccessToken } from '$lib/auth/session';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import PaymentAttemptForm from '$lib/components/registrations/PaymentAttemptForm.svelte';
	import StatusTimeline from '$lib/components/registrations/StatusTimeline.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { onMount } from 'svelte';

	let accessToken = $state<string | null>(null);
	let registration = $state<RegistrationRead | null>(null);
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
		return new Intl.DateTimeFormat(getLocale(), {
			dateStyle: 'medium',
			timeStyle: 'short'
		}).format(new Date(value));
	}

	function formatFee(): string {
		if (!registration) return '';
		return new Intl.NumberFormat(getLocale(), {
			style: 'currency',
			currency: registration.fee_currency_snapshot
		}).format(Number(registration.fee_amount_snapshot));
	}

	async function refreshRegistration(): Promise<void> {
		if (!accessToken) return;
		try {
			registration = await getRegistration(accessToken, Number(page.params.id));
			formErrors = [];
		} catch (cause) {
			if (isAuthenticationError(cause)) {
				redirectToSignIn(true);
				return;
			}
			({ formErrors } = formErrorsFrom(cause, m.registration_detail_load_failed()));
		}
	}

	onMount(async () => {
		accessToken = getAccessToken();
		if (!accessToken) {
			loading = false;
			redirectToSignIn(false);
			return;
		}

		try {
			await refreshRegistration();
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head>
	<title
		>{registration
			? m.registration_detail_heading({ id: registration.id })
			: m.nav_my_registrations()} · {m.app_title()}</title
	>
	<meta name="description" content={m.registration_detail_intro()} />
</svelte:head>

{#if loading || redirecting}
	<p
		class="border border-[var(--line)] bg-[var(--surface-muted)] p-6 text-sm text-[var(--text-muted)]"
		role="status"
	>
		{redirecting ? m.auth_redirecting_to_sign_in() : m.registration_detail_loading()}
	</p>
{:else if registration && accessToken}
	<article>
		<header
			class="grid border border-[var(--line)] lg:grid-cols-[minmax(0,1.45fr)_minmax(17rem,0.55fr)]"
		>
			<div class="p-5 sm:p-7 lg:p-9">
				<p class="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
					{registration.tournament_game.tournament_name}
				</p>
				<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
					{registration.team_name || registration.tournament_game.game_name}
				</h1>
				<p class="mt-4 text-base text-[var(--text-muted)]">
					{registration.tournament_game.game_name} · {m.registration_detail_heading({
						id: registration.id
					})}
				</p>
			</div>
			<dl
				class="grid gap-px border-t border-[var(--line)] bg-[var(--line)] text-sm lg:border-l lg:border-t-0"
			>
				<div class="bg-[var(--surface-muted)] p-5">
					<dt class="text-xs text-[var(--text-muted)]">{m.registration_status_label()}</dt>
					<dd
						class="mt-2 inline-block border border-[var(--accent)] px-2 py-1 text-xs font-semibold text-[var(--accent)]"
					>
						{statusLabel(registration.status)}
					</dd>
				</div>
				<div class="bg-[var(--surface-muted)] p-5">
					<dt class="text-xs text-[var(--text-muted)]">{m.registration_submitted_label()}</dt>
					<dd class="font-mono-data mt-1 text-xs font-semibold">
						<time datetime={registration.submitted_at}>{formatDate(registration.submitted_at)}</time
						>
					</dd>
				</div>
				<div class="bg-[var(--surface-muted)] p-5">
					<dt class="text-xs text-[var(--text-muted)]">{m.game_fee()}</dt>
					<dd class="font-mono-data mt-1 text-xs font-semibold">{formatFee()}</dd>
				</div>
			</dl>
		</header>

		<div class="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(16rem,0.6fr)]">
			<section aria-labelledby="registration-roster-heading">
				<header class="mb-4 flex items-center gap-3 border-b border-[var(--line)] pb-4">
					<span class="bracket-node" aria-hidden="true"></span>
					<h2 class="font-heading text-2xl font-semibold" id="registration-roster-heading">
						{m.roster_heading()}
					</h2>
				</header>
				<ol class="border border-[var(--line)]">
					{#each registration.members as member (member.display_order)}
						<li
							class="grid gap-3 border-b border-[var(--line)] p-4 last:border-b-0 sm:grid-cols-[4rem_minmax(0,1fr)_minmax(0,0.7fr)_auto] sm:items-center"
						>
							<span class="font-mono-data text-2xl font-semibold text-[var(--accent)]"
								>{String(member.display_order).padStart(2, '0')}</span
							>
							<span class="font-semibold">{member.gamer_tag_snapshot}</span>
							<span class="text-sm text-[var(--text-muted)]">{member.school_snapshot}</span>
							{#if member.is_captain}
								<span
									class="border border-[var(--accent)] px-2 py-1 text-xs font-semibold text-[var(--accent)]"
									>{m.roster_captain()}</span
								>
							{/if}
						</li>
					{/each}
				</ol>
			</section>

			<section
				class="border border-[var(--line)] p-5"
				aria-labelledby="registration-status-heading"
			>
				<h2 class="font-heading mb-5 text-xl font-semibold" id="registration-status-heading">
					{m.registration_status_history_heading()}
				</h2>
				<StatusTimeline events={registration.status_events} />
			</section>
		</div>

		{#if registration.payment_required}
			<div class="mt-8">
				<PaymentAttemptForm
					registrationId={registration.id}
					{accessToken}
					initialAmount={registration.fee_amount_snapshot}
					initialCurrency={registration.fee_currency_snapshot}
					onSuccess={refreshRegistration}
				/>
			</div>
		{/if}
	</article>
{:else}
	<section><ErrorSummary errors={formErrors} /></section>
{/if}
