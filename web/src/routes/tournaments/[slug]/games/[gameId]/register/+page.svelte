<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { ApiRequestError } from '$lib/api/client';
	import { submitRegistration } from '$lib/api/registrations';
	import type { RegistrationMemberInput } from '$lib/api/types';
	import { replaceInternalLocation } from '$lib/auth/navigation';
	import { clearSession, getAccessToken } from '$lib/auth/session';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import Field from '$lib/components/forms/Field.svelte';
	import TurnstileWidget from '$lib/components/forms/TurnstileWidget.svelte';
	import RosterEditor from '$lib/components/registrations/RosterEditor.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Card from '$lib/components/ui/card';
	import { Spinner } from '$lib/components/ui/spinner';
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let accessToken = $state<string | null>(null);
	let members = $state<RegistrationMemberInput[]>([]);
	let teamName = $state('');
	let turnstileToken = $state('');
	let turnstileWidget = $state<{ reset: () => void } | null>(null);
	let loading = $state(true);
	let submitting = $state(false);
	let redirecting = $state(false);
	let fieldErrors = $state<Record<string, string[]>>({});
	let formErrors = $state<string[]>([]);

	function signInHref(): string {
		const currentHref = `${page.url.pathname}${page.url.search}${page.url.hash}`;
		return `${resolve(localizeInternalHref('/auth/sign-in'))}?redirect=${encodeURIComponent(currentHref)}`;
	}

	function navigateToSignIn(clearTokens: boolean): void {
		if (redirecting) return;
		redirecting = true;
		if (clearTokens) clearSession();
		replaceInternalLocation(signInHref());
	}

	function isAuthenticationError(cause: unknown): boolean {
		return cause instanceof ApiRequestError && (cause.status === 401 || cause.status === 403);
	}

	function formatFee(): string {
		return new Intl.NumberFormat(getLocale(), {
			style: 'currency',
			currency: data.game.fee_currency
		}).format(Number(data.game.fee_amount));
	}

	onMount(() => {
		accessToken = getAccessToken();
		if (!accessToken) {
			navigateToSignIn(false);
			return;
		}

		loading = false;
	});

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting || !accessToken) return;
		if (!turnstileToken) {
			formErrors = [m.turnstile_required()];
			return;
		}

		submitting = true;
		fieldErrors = {};
		formErrors = [];

		try {
			const request = submitRegistration(
				accessToken,
				{
					tournament_game: data.game.id,
					team_name: data.game.team_size_max > 1 ? teamName : '',
					members
				},
				turnstileToken
			);
			turnstileWidget?.reset();
			const registration = await request;
			await goto(resolve(localizeInternalHref(`/account/registrations/${registration.id}`)));
		} catch (cause) {
			if (isAuthenticationError(cause)) {
				navigateToSignIn(true);
				return;
			}
			const nextErrors = formErrorsFrom(cause, m.registration_submit_failed());
			fieldErrors = nextErrors.fieldErrors;
			formErrors = [
				...nextErrors.formErrors,
				...Object.entries(nextErrors.fieldErrors).flatMap(([field, errors]) =>
					field === 'team_name' ? [] : errors
				)
			];
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>{m.registration_form_heading({ game: data.game.game_name })} · {m.app_title()}</title>
	<meta
		name="description"
		content={m.registration_form_intro({ tournament: data.tournament.name })}
	/>
</svelte:head>

<header class="grid border border-(--line) lg:grid-cols-[minmax(0,1.45fr)_minmax(17rem,0.55fr)]">
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
			{m.registration_form_kicker()}
		</p>
		<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
			{m.registration_form_heading({ game: data.game.game_name })}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-(--text-muted)">
			{m.registration_form_intro({ tournament: data.tournament.name })}
		</p>
	</div>
	<dl class="grid gap-px border-t border-(--line) bg-(--line) text-sm lg:border-l lg:border-t-0">
		<div class="bg-(--surface-muted) p-5">
			<dt class="text-xs text-(--text-muted)">{m.tournament_label()}</dt>
			<dd class="mt-1 font-semibold">{data.tournament.name}</dd>
		</div>
		<div class="bg-(--surface-muted) p-5">
			<dt class="text-xs text-(--text-muted)">{m.game_fee()}</dt>
			<dd class="font-mono-data mt-1 text-sm font-semibold">{formatFee()}</dd>
		</div>
	</dl>
</header>

{#if loading || redirecting}
	<p
		class="mt-8 border border-(--line) bg-(--surface-muted) p-6 text-sm text-(--text-muted)"
		role="status"
	>
		{m.auth_redirecting_to_sign_in()}
	</p>
{:else if accessToken}
	<form class="mt-8" aria-busy={submitting} onsubmit={handleSubmit}>
		<Card.Root class="gap-8">
			<Card.Content class="grid gap-8">
				<ErrorSummary errors={formErrors} />
				{#if data.game.team_size_max > 1}
					<Card.Root aria-labelledby="team-identity-heading">
						<Card.Header>
							<Card.Title role="heading" aria-level={2} id="team-identity-heading">
								{m.registration_team_heading()}
							</Card.Title>
						</Card.Header>
						<Card.Content>
							<Field
								label={m.field_team_name()}
								name="team_name"
								required
								maxlength={100}
								error={fieldErrors.team_name?.[0]}
								bind:value={teamName}
							/>
						</Card.Content>
					</Card.Root>
				{/if}

				<RosterEditor
					teamSizeMin={data.game.team_size_min}
					teamSizeMax={data.game.team_size_max}
					bind:members
				/>
				<TurnstileWidget
					bind:this={turnstileWidget}
					action="registration-submit"
					bind:token={turnstileToken}
				/>
			</Card.Content>
			<Card.Footer class="justify-end border-t">
				<Button class="min-h-11" type="submit" disabled={submitting}>
					{#if submitting}<Spinner aria-hidden="true" />{/if}
					{submitting ? m.registration_submitting() : m.action_submit_registration()}
				</Button>
			</Card.Footer>
		</Card.Root>
	</form>
{:else}
	<section class="mt-8"><ErrorSummary errors={formErrors} /></section>
{/if}
