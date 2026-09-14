<script lang="ts">
	import { onMount } from 'svelte';
	import { reservePaymentReference, getPaymentReference } from '$lib/api/registrations';
	import * as m from '$lib/paraglide/messages';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';

	let {
		gameId,
		registrationId,
		accessToken,
		initialReference = '',
		amount,
		currency,
		// eslint-disable-next-line no-useless-assignment -- Output binding initializes the parent before the request completes.
		token = $bindable(''),
		// eslint-disable-next-line no-useless-assignment -- Output binding initializes the parent before the request completes.
		ready = $bindable(false),
		errorMessage = ''
	}: {
		gameId?: number;
		registrationId?: number;
		accessToken?: string;
		initialReference?: string;
		amount: string;
		currency: string;
		token?: string;
		ready?: boolean;
		errorMessage?: string;
	} = $props();
	let reference = $state('');
	let loading = $state(true);
	let error = $state('');
	let copied = $state(false);

	async function initialize() {
		loading = true;
		ready = false;
		token = '';
		error = '';
		try {
			if (registrationId && accessToken) {
				reference =
					initialReference || (await getPaymentReference(accessToken, registrationId)).reference;
			} else if (gameId) {
				let saved: string | null = null;
				try {
					saved = sessionStorage.getItem(`usec-payment-intent:${gameId}`);
				} catch {
					/* Storage may be disabled. */
				}
				const intent = await reservePaymentReference(gameId, saved || undefined);
				reference = intent.reference;
				try {
					sessionStorage.setItem(`usec-payment-intent:${gameId}`, intent.token);
				} catch {
					/* Keep the current reference in memory. */
				}
				if (Number(intent.amount) !== Number(amount) || intent.currency !== currency) {
					error = m.payment_reference_fee_changed();
					return;
				}
				token = intent.token;
			}
			ready = !!reference;
		} catch {
			error = m.payment_reference_failed();
		} finally {
			loading = false;
		}
	}
	async function copy() {
		try {
			await navigator.clipboard.writeText(reference);
			copied = true;
		} catch {
			error = m.payment_reference_copy_failed();
		}
	}
	onMount(() => {
		void initialize();
	});
</script>

<Field.Field data-invalid={!!(error || errorMessage)}>
	<Field.Label for="payment-reference">{m.field_payment_reference()}</Field.Label>
	<div class="flex gap-2">
		<Input
			id="payment-reference"
			readonly
			value={reference}
			aria-describedby="payment-reference-hint"
			aria-busy={loading}
		/>
		<Button type="button" variant="outline" disabled={!reference || loading} onclick={copy}
			>{copied ? m.payment_reference_copied() : m.payment_reference_copy()}</Button
		>
	</div>
	<Field.Description id="payment-reference-hint"
		>{loading ? m.payment_reference_loading() : m.payment_reference_hint()}</Field.Description
	>
	{#if error || errorMessage}
		<Field.Error>{error || errorMessage}</Field.Error>
		{#if !reference}<Button type="button" variant="outline" disabled={loading} onclick={initialize}
				>{m.payment_reference_retry()}</Button
			>{/if}
	{/if}
</Field.Field>
