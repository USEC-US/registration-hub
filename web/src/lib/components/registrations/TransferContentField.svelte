<script lang="ts">
	import { onMount } from 'svelte';
	import { reservePaymentInstructions, getPaymentInstructions } from '$lib/api/registrations';
	import * as m from '$lib/paraglide/messages';
	import * as Field from '$lib/components/ui/field';
	import { transferContent } from './transfer-content';
	import { Button } from '$lib/components/ui/button';

	let {
		gameId,
		registrationId,
		accessToken,
		participant = '',
		amount,
		currency,
		// eslint-disable-next-line no-useless-assignment -- Output binding initializes the parent before the request completes.
		token = $bindable(''),
		ready = $bindable(false),
		errorMessage = ''
	}: {
		gameId?: number;
		registrationId?: number;
		accessToken?: string;
		participant?: string;
		amount: string;
		currency: string;
		token?: string;
		ready?: boolean;
		errorMessage?: string;
	} = $props();
	let template = $state('');
	let savedContent = $state('');
	let limit = $state(100);
	let issuedToken = $state('');
	let loaded = $state(false);
	let content = $derived(registrationId ? savedContent : transferContent(template, participant));
	let contentLength = $derived(Array.from(content).length);
	let needsParticipant = $derived(
		!registrationId &&
			(template.match(/{{|}}|{participant}/g)?.includes('{participant}') ?? false) &&
			!participant.trim()
	);
	let contentError = $derived(
		needsParticipant
			? m.transfer_content_participant_required()
			: contentLength > limit
				? m.transfer_content_too_long({ limit })
				: ''
	);
	$effect(() => {
		ready = loaded && !error && !contentError;
		token = ready ? issuedToken : '';
	});
	let loading = $state(true);
	let error = $state('');
	let copiedContent = $state('');
	let copyError = $state('');

	async function initialize() {
		loading = true;
		loaded = false;
		issuedToken = '';
		copiedContent = '';
		copyError = '';
		error = '';
		try {
			if (registrationId && accessToken) {
				const instructions = await getPaymentInstructions(accessToken, registrationId);
				savedContent = instructions.transfer_content;
				limit = instructions.transfer_content_limit;
			} else if (gameId) {
				let saved: string | null = null;
				try {
					saved = sessionStorage.getItem(`usec-payment-intent:${gameId}`);
				} catch {
					/* Storage may be disabled. */
				}
				const intent = await reservePaymentInstructions(gameId, saved || undefined);
				template = intent.transfer_content_template;
				limit = intent.transfer_content_limit;
				try {
					sessionStorage.setItem(`usec-payment-intent:${gameId}`, intent.token);
				} catch {
					/* Keep the current payment session in memory. */
				}
				if (Number(intent.amount) !== Number(amount) || intent.currency !== currency) {
					error = m.transfer_content_fee_changed();
					return;
				}
				issuedToken = intent.token;
			}
			loaded = true;
		} catch {
			error = m.transfer_content_failed();
		} finally {
			loading = false;
		}
	}
	async function copy() {
		try {
			await navigator.clipboard.writeText(content);
			copiedContent = content;
			copyError = '';
		} catch {
			copyError = m.transfer_content_copy_failed();
		}
	}
	onMount(() => {
		void initialize();
	});
</script>

<Field.Field data-invalid={!!(error || (!needsParticipant && contentError) || errorMessage)}>
	<Field.Label for="transfer-content">{m.field_transfer_content()}</Field.Label>
	<output
		id="transfer-content"
		class="rounded-md border border-input bg-transparent px-3 py-3 text-sm break-words"
		aria-describedby="transfer-content-hint"
		aria-busy={loading}
	>
		{needsParticipant
			? m.transfer_content_participant_required()
			: content || (loading ? m.transfer_content_loading() : m.transfer_content_legacy())}
	</output>
	<div class="flex items-center justify-between gap-3">
		<Field.Description>{contentLength}/{limit}</Field.Description>
		<Button
			type="button"
			variant="outline"
			disabled={!content || loading || !!contentError || !!error}
			onclick={copy}
		>
			{copiedContent && copiedContent === content
				? m.transfer_content_copied()
				: m.transfer_content_copy()}
		</Button>
	</div>
	<Field.Description id="transfer-content-hint">
		{loading ? m.transfer_content_loading() : m.transfer_content_hint()}
	</Field.Description>
	{#if copyError}<Field.Error>{copyError}</Field.Error>{/if}
	{#if error || (!needsParticipant && contentError) || errorMessage}
		<Field.Error>{error || contentError || errorMessage}</Field.Error>
		{#if error}<Button type="button" variant="outline" disabled={loading} onclick={initialize}
				>{m.transfer_content_retry()}</Button
			>{/if}
	{/if}
</Field.Field>
