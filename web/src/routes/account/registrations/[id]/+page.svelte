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
	import { Badge } from '$lib/components/ui/badge';
	import * as Card from '$lib/components/ui/card';
	import { Skeleton } from '$lib/components/ui/skeleton';
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

	function statusClass(status: RegistrationStatus): string {
		switch (status) {
			case 'APPROVED':
				return 'border-success text-success';
			case 'REJECTED':
				return 'border-destructive text-destructive';
			default:
				return '';
		}
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
	<section class="flex flex-col gap-4" role="status">
		<p class="text-sm text-muted-foreground">
			{redirecting ? m.auth_redirecting_to_sign_in() : m.registration_detail_loading()}
		</p>
		<Skeleton class="h-48 w-full" />
		<Skeleton class="h-64 w-full" />
	</section>
{:else if registration && accessToken}
	<article>
		<Card.Root class="grid gap-0 py-0 lg:grid-cols-[minmax(0,1.45fr)_minmax(17rem,0.55fr)]">
			<Card.Header class="p-5 sm:p-7 lg:row-span-2 lg:p-9">
				<p class="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
					{registration.tournament_game.tournament_name}
				</p>
				<Card.Title class="mt-3"><h1>{registration.team_name || registration.tournament_game.game_name}</h1></Card.Title>
				<Card.Description class="mt-4 text-base">
					{registration.tournament_game.game_name} · {m.registration_detail_heading({
						id: registration.id
					})}
				</Card.Description>
			</Card.Header>
			<Card.Content class="p-0">
				<dl class="grid gap-px bg-border text-sm">
					<div class="bg-muted p-5">
						<dt class="text-xs text-(--text-muted)">{m.registration_status_label()}</dt>
						<dd class="mt-2"><Badge variant={registration.status === 'REJECTED' ? 'destructive' : 'outline'} class={statusClass(registration.status)}>{statusLabel(registration.status)}</Badge></dd>
					</div>
					<div class="bg-muted p-5">
						<dt class="text-xs text-(--text-muted)">{m.registration_submitted_label()}</dt>
					<dd class="font-mono-data mt-1 text-xs font-semibold">
						<time datetime={registration.submitted_at}>{formatDate(registration.submitted_at)}</time
						>
					</dd>
				</div>
					<div class="bg-muted p-5">
					<dt class="text-xs text-(--text-muted)">{m.game_fee()}</dt>
					<dd class="font-mono-data mt-1 text-xs font-semibold">{formatFee()}</dd>
					</div>
				</dl>
			</Card.Content>
		</Card.Root>

		<div class="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(16rem,0.6fr)]">
			<Card.Root aria-labelledby="registration-roster-heading">
				<Card.Header>
					<Card.Title><h2 id="registration-roster-heading">{m.roster_heading()}</h2></Card.Title>
				</Card.Header>
				<Card.Content class="p-0">
				<ol class="divide-y">
					{#each registration.members as member (member.display_order)}
						<li
							class="grid gap-3 p-4 sm:grid-cols-[4rem_minmax(0,1fr)_minmax(0,0.7fr)_auto] sm:items-center"
						>
							<span class="font-mono-data text-2xl font-semibold text-accent"
								>{String(member.display_order).padStart(2, '0')}</span
							>
							<span class="font-semibold">{member.gamer_tag_snapshot}</span>
							<span class="text-sm text-(--text-muted)">{member.school_snapshot}</span>
							{#if member.is_captain}
								<Badge variant="outline">{m.roster_captain()}</Badge>
							{/if}
						</li>
					{/each}
				</ol>
				</Card.Content>
			</Card.Root>

			<Card.Root aria-labelledby="registration-status-heading">
				<Card.Header>
					<Card.Title><h2 id="registration-status-heading">{m.registration_status_history_heading()}</h2></Card.Title>
				</Card.Header>
				<Card.Content><StatusTimeline events={registration.status_events} /></Card.Content>
			</Card.Root>
		</div>

		{#if registration.payment_required}
			<div class="mt-8">
				<PaymentAttemptForm
					registrationId={registration.id}
					{accessToken}
					initialAmount={registration.fee_amount_snapshot}
					initialCurrency={registration.fee_currency_snapshot}
					onSuccess={refreshRegistration}
					onAuthenticationError={() => redirectToSignIn(true)}
				/>
			</div>
		{/if}
	</article>
{:else}
	<section><ErrorSummary errors={formErrors} /></section>
{/if}
