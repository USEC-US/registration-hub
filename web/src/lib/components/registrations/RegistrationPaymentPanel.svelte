<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import {
		getPaymentSession,
		uploadPaymentProof,
		type RegistrationAccessOptions
	} from '$lib/api/registrations';
	import { searchInstitutions } from '$lib/api/institutions';
	import { getTournament } from '$lib/api/tournaments';
	import type { RegistrationPaymentSession } from '$lib/api/types';
	import {
		getRegistrationStorage,
		readDraft,
		writeDraft
	} from '$lib/registrations/browser-storage';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import * as Alert from '$lib/components/ui/alert';
	import PaymentProofField from './PaymentProofField.svelte';
	import TurnstileWidget from '$lib/components/forms/TurnstileWidget.svelte';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import StatusTimeline from './StatusTimeline.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	let {
		session,
		authority,
		onupdated
	}: {
		session: RegistrationPaymentSession;
		authority: RegistrationAccessOptions;
		onupdated: (session: RegistrationPaymentSession) => void;
	} = $props();
	let busy = $state(false),
		errors = $state<string[]>([]),
		copyStatus = $state(''),
		file = $state<File | undefined>(),
		selectionError = $state(''),
		token = $state('');
	let widget = $state<{ reset: () => void } | null>(null);
	let remaining = $state(0),
		atBoundary = $state(false),
		retryAvailable = $state(false),
		storageWarning = $state(false);
	let active = true;
	let baseline = 0,
		serverEpoch = 0,
		refreshedBoundary = false;
	const terminal = $derived(
		session.expired ||
			session.registration.status === 'EXPIRED' ||
			session.registration.status === 'REJECTED'
	);
	const actionable = $derived(
		!terminal &&
			!atBoundary &&
			session.can_upload_proof &&
			['UNPAID', 'REJECTED'].includes(session.payment_state)
	);
	$effect(() => {
		const current = session;
		untrack(() => {
			serverEpoch = Date.parse(current.server_now);
			baseline = performance.now();
			refreshedBoundary = false;
			atBoundary = false;
			updateClock();
		});
	});

	function updateClock() {
		if (!session.payment_due_at) {
			remaining = 0;
			return;
		}
		remaining = Math.max(
			0,
			Math.ceil(
				(Date.parse(session.payment_due_at) - (serverEpoch + performance.now() - baseline)) / 1000
			)
		);
		if (remaining === 0 && session.can_upload_proof && !refreshedBoundary) {
			atBoundary = true;
			refreshedBoundary = true;
			void refresh();
		}
	}
	async function refresh() {
		if (!active || busy) return;
		busy = true;
		try {
			const next = await getPaymentSession(session.registration.id, authority);
			if (!active) return;
			onupdated(next);
			errors = [];
		} catch (cause) {
			errors = formErrorsFrom(cause, m.registration_detail_load_failed()).formErrors;
		} finally {
			busy = false;
		}
	}
	onMount(() => {
		const interval = setInterval(updateClock, 1000);
		const visible = () => {
			if (document.visibilityState === 'visible') void refresh();
		};
		document.addEventListener('visibilitychange', visible);
		return () => {
			active = false;
			clearInterval(interval);
			document.removeEventListener('visibilitychange', visible);
		};
	});
	$effect(() => {
		if (terminal) {
			void getTournament(session.tournament_slug)
				.then((tournament) => {
					if (!active) return;
					const game = tournament.tournament_games.find(
						(g) => g.id === session.registration.tournament_game.id
					);
					retryAvailable = Boolean(
						game?.is_registration_open &&
						(game.capacity_remaining === null || game.capacity_remaining > 0) &&
						(Number(game.fee_amount) === 0 || game.payment_available)
					);
				})
				.catch(() => {
					retryAvailable = false;
				});
		}
	});
	async function copy(text: string) {
		try {
			await navigator.clipboard.writeText(text);
			copyStatus = m.payment_copied();
		} catch {
			copyStatus = m.payment_copy_failed();
		}
	}
	async function upload(event: SubmitEvent) {
		event.preventDefault();
		if (!actionable || busy) return;
		if (selectionError || !file) {
			errors = [selectionError || m.payment_evidence_required()];
			return;
		}
		if (!token) {
			errors = [m.turnstile_required()];
			return;
		}
		busy = true;
		try {
			const form = new FormData();
			form.append('proof_file', file);
			form.append('turnstile_token', token);
			const request = uploadPaymentProof(session.registration.id, form, authority);
			widget?.reset();
			const next = await request;
			if (!active) return;
			file = undefined;
			errors = [];
			onupdated(next);
		} catch (cause) {
			const result = formErrorsFrom(cause, m.registration_submit_failed());
			errors = [...result.formErrors, ...Object.values(result.fieldErrors).flat()];
		} finally {
			busy = false;
		}
	}
	async function retry() {
		const storage = getRegistrationStorage();
		const existing = readDraft(
			storage.storage,
			session.registration.tournament_game.id,
			Date.now()
		);
		if (existing) {
			errors = [m.payment_retry_existing()];
			return;
		}
		const fields = structuredClone($state.snapshot(session.saved_submission));
		try {
			fields.members = await Promise.all(
				fields.members.map(async (member) => {
					member = { ...member, date_of_birth_snapshot: member.date_of_birth_snapshot ?? '' };
					if (!member.institution_id) return member;
					const label = session.institution_labels[String(member.display_order)] ?? '';
					const choices = await searchInstitutions(label);
					if (choices.some((choice) => choice.id === member.institution_id)) return member;
					const { institution_id, ...identity } = member;
					void institution_id;
					return { ...identity, institution_label: '' };
				})
			);
		} catch {
			errors = [m.registration_submit_failed()];
			return;
		}

		if (!active) return;
		writeDraft(storage.storage, {
			version: 1,
			gameId: fields.tournament_game,
			updatedAt: Date.now(),
			stage: 'details',
			fields,
			institutionLabels: session.institution_labels
		});
		storageWarning = Boolean(storage.persistenceWarning);
		await goto(
			resolve(
				localizeInternalHref(
					`/tournaments/${session.tournament_slug}/games/${fields.tournament_game}/register`
				)
			)
		);
	}
	async function download() {
		const instructions = session.instructions;
		if (!actionable || !instructions?.qr_png_data_url) return;
		try {
			const img = new Image();
			img.src = instructions.qr_png_data_url;
			await img.decode();
			if (!active) return;
			const canvas = document.createElement('canvas');
			canvas.width = 800;
			const ctx = canvas.getContext('2d');
			if (!ctx) return;
			const lines = [
				instructions.bank_name,
				instructions.account_holder,
				instructions.account_number,
				`${instructions.amount} ${instructions.currency}`,
				instructions.qr_contains_transfer_content
					? m.field_transfer_content()
					: m.payment_qr_fallback(),
				instructions.transfer_content
			];
			ctx.font = '24px sans-serif';
			const wrapped: string[] = [];
			for (const line of lines) {
				let part = '';
				for (const char of line) {
					if (ctx.measureText(part + char).width > 736) {
						wrapped.push(part);
						part = '';
					}
					part += char;
				}
				wrapped.push(part);
			}
			canvas.height = 640 + wrapped.length * 34;
			ctx.fillStyle = 'white';
			ctx.fillRect(0, 0, canvas.width, canvas.height);
			ctx.drawImage(img, 120, 24, 560, 560);
			ctx.fillStyle = 'black';
			ctx.font = '24px sans-serif';
			wrapped.forEach((line, index) => ctx.fillText(line, 32, 630 + index * 34));
			const anchor = document.createElement('a');
			anchor.href = canvas.toDataURL('image/png');
			anchor.download = `registration-${session.registration.id}-payment.png`;
			anchor.click();
		} catch {
			errors = [m.payment_copy_failed()];
		}
	}
</script>

<Card.Root
	><Card.Header
		><Card.Title><h2>{m.payment_page()}</h2></Card.Title><Card.Description
			>{m.registration_reference({ id: session.registration.id })} · {session.registration
				.team_name}</Card.Description
		></Card.Header
	>
	<Card.Content class="flex min-w-0 flex-col gap-5 break-words">
		<ErrorSummary {errors} />
		{#if storageWarning}<p role="alert">{m.stages_storage()}</p>{/if}
		{#if terminal}<Alert.Root variant="destructive"
				><Alert.Description
					><p>{m.payment_expired()}</p>
					<p>{m.payment_terminal_contact()}</p>
					<a class="underline" href="https://facebook.com/hcmusec"
						>{m.registration_contact_organizers()}</a
					></Alert.Description
				></Alert.Root
			>
		{:else if session.payment_state === 'PENDING'}<p role="status">{m.payment_pending_review()}</p>
		{:else if session.payment_state === 'VERIFIED'}<p role="status">
				{m.payment_verified_review()}
			</p>
		{:else if session.payment_state === 'NOT_REQUIRED'}<p>{m.payment_free()}</p>{/if}
		{#if !terminal && session.payment_state === 'UNPAID'}<p>
				{m.payment_unpaid()}
			</p>{:else if !terminal && session.payment_state === 'REJECTED'}<p>
				{m.payment_proof_rejected()}
			</p>{/if}
		{#if session.replacement_note}<Alert.Root
				><Alert.Title>{m.status_REJECTED()}</Alert.Title><Alert.Description
					>{session.replacement_note}</Alert.Description
				></Alert.Root
			>{/if}
		{#if session.payment_due_at}<p>
				{m.payment_deadline()}:
				<time datetime={session.payment_due_at}
					>{new Date(session.payment_due_at).toLocaleString(getLocale())}</time
				>
			</p>
			{#if actionable}<p>{m.payment_remaining({ seconds: remaining })}</p>{/if}{/if}
		{#if actionable}
			{#if session.instructions?.bank_name && session.instructions.account_number}
				{@const instructions = session.instructions}
				<dl class="grid gap-4 sm:grid-cols-2">
					{#each [[m.payment_bank(), instructions.bank_name], [m.payment_account(), instructions.account_number], [m.payment_holder(), instructions.account_holder], [m.game_fee(), `${instructions.amount} ${instructions.currency}`], [m.field_transfer_content(), instructions.transfer_content]] as [label, value] (label)}<div
							class="min-w-0"
						>
							<dt class="text-sm text-muted-foreground">{label}</dt>
							<dd class="whitespace-pre-wrap break-all">{value}</dd>
							<Button
								size="sm"
								variant="outline"
								aria-label={`${m.payment_copy()} ${label}`}
								onclick={() => copy(value)}>{m.payment_copy()}</Button
							>
						</div>{/each}
				</dl>
				{#if !instructions.qr_contains_transfer_content}<Alert.Root
						><Alert.Title>{m.payment_qr_fallback()}</Alert.Title></Alert.Root
					>{/if}
				{#if instructions.qr_png_data_url}<img
						class="mx-auto h-auto w-full max-w-80"
						src={instructions.qr_png_data_url}
						alt={m.payment_qr_alt()}
					/><Button variant="outline" onclick={download}>{m.payment_qr_download()}</Button>{/if}
			{:else}<p>{m.payment_historical()}</p>
				{#if session.instructions?.transfer_content}<p>
						{session.instructions.transfer_content}
					</p>{/if}{/if}
			<form onsubmit={upload} class="flex flex-col gap-4">
				<PaymentProofField required disabled={busy} bind:file bind:selectionError /><TurnstileWidget
					action="payment-proof-submit"
					bind:this={widget}
					bind:token
				/><Button type="submit" disabled={busy || Boolean(selectionError)}
					>{m.action_upload_payment_proof()}</Button
				>
			</form>
		{/if}
		<p role="status">{copyStatus}</p>
		<StatusTimeline events={session.registration.status_events} />
		{#if terminal && retryAvailable}<p>{m.payment_retry_hint()}</p>
			<Button onclick={retry}>{m.payment_retry()}</Button>{/if}
	</Card.Content><Card.Footer
		><Button variant="outline" disabled={busy} onclick={refresh}>{m.payment_refresh()}</Button
		></Card.Footer
	></Card.Root
>
