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
	import * as m from '$lib/paraglide/messages';

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
	><title>{m.payment_page()} · {m.app_title()}</title><meta
		name="robots"
		content="noindex,nofollow"
	/></svelte:head
>
<h1 class="mb-6 font-heading text-3xl font-semibold">{m.payment_page()}</h1>
{#if warning}<p role="alert">{m.stages_storage()}</p>{/if}
{#if loading}<p role="status">
		{m.registration_loading()}
	</p>{:else if session && authority}<RegistrationPaymentPanel
		{session}
		{authority}
		onupdated={(next) => {
			if (active) session = next;
		}}
	/>{#if authority.credential}<p class="mt-4">{m.stages_forget_hint()}</p>
		<Button variant="ghost" onclick={forget}>{m.stages_forget()}</Button
		>{/if}{:else if temporaryFailure}<p role="alert">{m.payment_load_temporary()}</p>
	<Button onclick={load}>{m.payment_load_retry()}</Button>{:else}<p role="alert">
		{m.payment_recovery()}
	</p>
	<a class="underline" href="https://facebook.com/hcmusec">{m.registration_contact_organizers()}</a
	>{/if}
