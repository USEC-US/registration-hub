<script lang="ts">
	import { onMount } from 'svelte';
	import { ApiRequestError } from '$lib/api/client';
	import { getAccessToken } from '$lib/auth/session';
	import { getPaymentSession, type RegistrationAccessOptions } from '$lib/api/registrations';
	import type { RegistrationPaymentSession } from '$lib/api/types';
	import {
		getRegistrationStorage,
		findSubmittedAccess,
		forgetAccess
	} from '$lib/registrations/browser-storage';
	import RegistrationPaymentPanel from '$lib/components/registrations/RegistrationPaymentPanel.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Alert from '$lib/components/ui/alert';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as m from '$lib/paraglide/messages';
	import WalletCards from '@lucide/svelte/icons/wallet-cards';

	let { registrationId }: { registrationId: number } = $props();
	let active = true;
	let loadGeneration = 0;
	let temporaryFailure = $state(false);
	let session = $state<RegistrationPaymentSession | null>(null),
		authority = $state<RegistrationAccessOptions | null>(null),
		loading = $state(true),
		warning = $state(false);
	onMount(() => {
		void load();
		return () => {
			active = false;
			loadGeneration++;
		};
	});
	async function load() {
		const generation = ++loadGeneration;
		loading = true;
		temporaryFailure = false;
		session = null;
		const context = getRegistrationStorage();
		const saved = findSubmittedAccess(context.storage, registrationId);
		try {
			const token = saved ? null : getAccessToken();
			authority = saved ? { credential: saved.credential } : token ? { accessToken: token } : null;
			if (authority) {
				const next = await getPaymentSession(registrationId, authority);
				if (active && generation === loadGeneration) session = next;
			}
		} catch (cause) {
			if (!active || generation !== loadGeneration) return;
			session = null;
			temporaryFailure = !(
				cause instanceof ApiRequestError && [400, 401, 403, 404].includes(cause.status)
			);
		} finally {
			if (active && generation === loadGeneration) {
				warning = Boolean(context.persistenceWarning);
				loading = false;
			}
		}
	}

	function forget() {
		if (authority?.credential) {
			const context = getRegistrationStorage();
			forgetAccess(context.storage, authority.credential);
			warning = Boolean(context.persistenceWarning);
			session = null;
			authority = null;
		}
	}
</script>

<svelte:head
	><title>{m.payment_page()} | {m.app_title()}</title><meta
		name="robots"
		content="noindex,nofollow"
	/></svelte:head
>
<div class="mx-auto flex max-w-6xl flex-col gap-7 sm:gap-8">
	<header class="flex items-start gap-4">
		<div
			class="hidden size-14 shrink-0 items-center justify-center rounded-2xl border bg-muted/50 sm:flex"
		>
			<WalletCards class="size-7 text-primary" aria-hidden="true" />
		</div>
		<div class="flex min-w-0 flex-col gap-2">
			{#if session}
				<p class="text-xs font-semibold tracking-wide text-muted-foreground">
					{session.registration.tournament_game.tournament_name}
				</p>
			{/if}
			<h1 class="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
				{m.payment_page()}
			</h1>
			{#if session}
				<p class="text-sm leading-relaxed text-muted-foreground">
					{session.registration.tournament_game.game_name} | {m.field_payment_reference()}:
					{session.registration.payment_reference}
				</p>
			{/if}
		</div>
	</header>

	{#if warning}
		<Alert.Root><Alert.Description>{m.stages_storage()}</Alert.Description></Alert.Root>
	{/if}
	{#if loading}
		<div role="status" class="flex flex-col gap-6">
			<span class="sr-only">{m.registration_loading()}</span>
			<Skeleton class="h-32 w-full rounded-xl" />
			<Skeleton class="h-96 w-full rounded-xl" />
		</div>
	{:else if session && authority}
		<RegistrationPaymentPanel
			{session}
			{authority}
			onupdated={(next) => {
				if (active) session = next;
			}}
		/>
		{#if authority.credential}
			<div
				class="flex flex-col items-start gap-2 rounded-xl border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between"
			>
				<p class="text-sm text-muted-foreground">{m.stages_forget_hint()}</p>
				<Button variant="ghost" onclick={forget}>{m.stages_forget()}</Button>
			</div>
		{/if}
	{:else if temporaryFailure}
		<Alert.Root>
			<Alert.Description>{m.payment_load_temporary()}</Alert.Description>
			<Button class="mt-3 w-fit" onclick={load}>{m.payment_load_retry()}</Button>
		</Alert.Root>
	{:else}
		<Alert.Root>
			<Alert.Description>{m.payment_recovery()}</Alert.Description>
			<a class="mt-3 underline underline-offset-4" href="https://facebook.com/hcmusec"
				>{m.registration_contact_organizers()}</a
			>
		</Alert.Root>
	{/if}
</div>
