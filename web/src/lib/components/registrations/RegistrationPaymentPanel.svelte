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
	import { paymentStatusMessage } from '$lib/registrations/payment-status';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import * as Alert from '$lib/components/ui/alert';
	import { Separator } from '$lib/components/ui/separator';
	import Clock3 from '@lucide/svelte/icons/clock-3';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import QrCode from '@lucide/svelte/icons/qr-code';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
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
	function formatRemaining(seconds: number): string {
		if (seconds < 60) return m.payment_less_than_minute();
		const totalMinutes = Math.ceil(seconds / 60);
		const hours = Math.floor(totalMinutes / 60);
		const minutes = totalMinutes % 60;
		const units = (value: number, unit: 'hour' | 'minute') =>
			new Intl.NumberFormat(getLocale(), {
				style: 'unit',
				unit,
				unitDisplay: 'short'
			}).format(value);
		return [hours && units(hours, 'hour'), minutes && units(minutes, 'minute')]
			.filter(Boolean)
			.join(' ');
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

<div class="flex min-w-0 flex-col gap-6">
	<Card.Root class="rounded-xl py-6" aria-labelledby="payment-panel-heading">
		<Card.Header>
			<div class="flex items-start gap-3">
				<span
					class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono-data text-sm font-semibold text-primary"
					aria-hidden="true">04</span
				>
				<div class="flex min-w-0 flex-col gap-1">
					<Card.Title
						><h2 id="payment-panel-heading">
							{session.payment_state === 'PENDING'
								? m.registration_confirmed_heading()
								: m.payment_page()}
						</h2></Card.Title
					>
					<Card.Description class="wrap-break-word"
						>{m.registration_reference({
							id: session.registration.id
						})}{#if session.registration.team_name}
							- {session.registration.team_name}{/if}</Card.Description
					>
				</div>
			</div>
		</Card.Header>
		<Card.Content class="flex min-w-0 flex-col gap-6 wrap-break-word">
			<ErrorSummary {errors} />
			{#if storageWarning}<Alert.Root
					><Alert.Description>{m.stages_storage()}</Alert.Description></Alert.Root
				>{/if}

			{#if terminal}
				<Alert.Root variant="destructive">
					<Alert.Title>{m.payment_expired()}</Alert.Title>
					<Alert.Description>
						<p>{m.payment_terminal_contact()}</p>
						<a class="underline underline-offset-4" href="https://facebook.com/hcmusec"
							>{m.registration_contact_organizers()}</a
						>
					</Alert.Description>
				</Alert.Root>
			{:else if session.payment_state === 'PENDING'}
				<Alert.Root role="status">
					<Alert.Title>{m.payment_pending_heading()}</Alert.Title>
					<Alert.Description>
						<p>{m.payment_pending_review()}</p>
						<p>{m.payment_pending_follow_up()}</p>
						<p class="flex flex-wrap gap-x-4 gap-y-1">
							<a href="https://facebook.com/hcmusec">{m.registration_contact_organizers()}</a>
							<a href="mailto:hcmusec@gmail.com">hcmusec@gmail.com</a>
						</p>
					</Alert.Description>
				</Alert.Root>
			{:else if session.payment_state === 'VERIFIED' || session.payment_state === 'NOT_REQUIRED'}
				<Alert.Root role="status"
					><Alert.Title>{paymentStatusMessage(session.registration)}</Alert.Title></Alert.Root
				>
			{/if}

			{#if !terminal && session.payment_state === 'UNPAID'}
				<p class="font-medium">{m.payment_unpaid()}</p>
			{:else if !terminal && session.payment_state === 'REJECTED'}
				<p class="font-medium">{m.payment_proof_rejected()}</p>
			{/if}

			{#if session.replacement_note}
				<Alert.Root>
					<Alert.Title>{m.status_REJECTED()}</Alert.Title>
					<Alert.Description>{session.replacement_note}</Alert.Description>
				</Alert.Root>
			{/if}

			{#if actionable && session.payment_due_at}
				<div class="flex flex-col gap-3 rounded-lg bg-muted/30 p-4 sm:flex-row sm:items-center">
					<span
						class="flex size-10 shrink-0 items-center justify-center rounded-full bg-background text-primary"
						aria-hidden="true"><Clock3 class="size-5" /></span
					>
					<div class="flex min-w-0 flex-1 flex-col gap-1">
						<p class="text-xs font-medium text-muted-foreground">{m.payment_deadline()}</p>
						<time class="font-mono-data text-sm font-semibold" datetime={session.payment_due_at}
							>{new Date(session.payment_due_at).toLocaleString(getLocale())}</time
						>
					</div>
					{#if actionable}
						<p class="font-mono-data text-base font-semibold text-primary" role="timer">
							{m.payment_remaining({ duration: formatRemaining(remaining) })}
						</p>
					{/if}
				</div>
			{/if}

			{#if actionable}
				<section class="flex min-w-0 flex-col gap-4" aria-labelledby="payment-instructions-heading">
					<div class="flex flex-col gap-1">
						<h3 id="payment-instructions-heading" class="font-heading text-lg font-semibold">
							{m.payment_instructions_heading()}
						</h3>
					</div>
					{#if session.instructions?.bank_name && session.instructions.account_number}
						{@const instructions = session.instructions}
						<div class="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
							<div class="flex min-w-0 flex-col gap-4">
								<dl class="grid gap-3 sm:grid-cols-2">
									{#each [[m.payment_bank(), instructions.bank_name], [m.payment_account(), instructions.account_number], [m.payment_holder(), instructions.account_holder], [m.game_fee(), `${instructions.amount} ${instructions.currency}`]] as [label, value] (label)}
										<div
											class="flex min-w-0 items-start justify-between gap-3 rounded-lg border p-4"
										>
											<div class="min-w-0">
												<dt class="text-xs text-muted-foreground">{label}</dt>
												<dd class="mt-1 whitespace-pre-wrap break-all font-medium">{value}</dd>
											</div>
											<Button
												size="sm"
												variant="outline"
												aria-label={`${m.payment_copy()} ${label}`}
												onclick={() => copy(value)}
												><Copy
													data-icon="inline-start"
													aria-hidden="true"
												/>{m.payment_copy()}</Button
											>
										</div>
									{/each}
								</dl>
								<div class="flex min-w-0 flex-col gap-3 rounded-lg border p-4">
									<div>
										<p class="text-xs text-muted-foreground">{m.field_transfer_content()}</p>
										<p
											class="mt-1 whitespace-pre-wrap wrap-break-word font-mono-data font-semibold"
										>
											{instructions.transfer_content}
										</p>
									</div>
									<Button
										class="w-fit"
										size="sm"
										variant="outline"
										aria-label={`${m.payment_copy()} ${m.field_transfer_content()}`}
										onclick={() => copy(instructions.transfer_content)}
										><Copy data-icon="inline-start" aria-hidden="true" />{m.payment_copy()}</Button
									>
								</div>
								{#if !instructions.qr_contains_transfer_content}
									<Alert.Root>
										<Alert.Description>{m.payment_qr_fallback()}</Alert.Description>
									</Alert.Root>
								{/if}
							</div>

							{#if instructions.qr_png_data_url}
								<Card.Root size="sm" class="h-fit rounded-xl">
									<Card.Header>
										<div class="flex items-center gap-2">
											<QrCode class="size-4 text-primary" aria-hidden="true" />
											<Card.Title>{m.payment_qr_alt()}</Card.Title>
										</div>
									</Card.Header>
									<Card.Content>
										<img
											class="mx-auto h-auto w-full max-w-64"
											src={instructions.qr_png_data_url}
											alt={m.payment_qr_alt()}
										/>
									</Card.Content>
									<Card.Footer>
										<Button class="w-full" variant="outline" onclick={download}
											><Download
												data-icon="inline-start"
												aria-hidden="true"
											/>{m.payment_qr_download()}</Button
										>
									</Card.Footer>
								</Card.Root>
							{/if}
						</div>
					{:else}
						<p>{m.payment_historical()}</p>
						{#if session.instructions?.transfer_content}
							<p class="whitespace-pre-wrap wrap-break-word font-mono-data">
								{session.instructions.transfer_content}
							</p>
						{/if}
					{/if}
				</section>

				<Separator />

				<section class="flex flex-col gap-4" aria-labelledby="payment-proof-heading">
					<div class="flex flex-col gap-1">
						<h3 id="payment-proof-heading" class="font-heading text-lg font-semibold">
							{m.payment_attempt_heading()}
						</h3>
						<p class="text-sm text-muted-foreground">{m.payment_attempt_intro()}</p>
					</div>
					<form onsubmit={upload} class="flex flex-col gap-4">
						<PaymentProofField required disabled={busy} bind:file bind:selectionError />
						<TurnstileWidget action="payment-proof-submit" bind:this={widget} bind:token />
						<Button type="submit" disabled={busy || Boolean(selectionError)}
							>{busy ? m.payment_uploading() : m.action_upload_payment_proof()}</Button
						>
					</form>
				</section>
			{/if}

			{#if copyStatus}<p role="status" class="text-sm text-muted-foreground">{copyStatus}</p>{/if}
			{#if terminal && retryAvailable}
				<Separator />
				<div class="flex flex-col items-start gap-3">
					<p class="text-sm text-muted-foreground">{m.payment_retry_hint()}</p>
					<Button onclick={retry}>{m.payment_retry()}</Button>
				</div>
			{/if}
		</Card.Content>
		<Card.Footer class="border-t">
			<Button variant="outline" disabled={busy} onclick={refresh}
				><RefreshCw data-icon="inline-start" aria-hidden="true" />{m.payment_refresh()}</Button
			>
		</Card.Footer>
	</Card.Root>

	<Card.Root class="rounded-xl py-6" aria-labelledby="payment-status-heading">
		<Card.Header>
			<Card.Title><h2 id="payment-status-heading">{m.status_timeline_label()}</h2></Card.Title>
		</Card.Header>
		<Card.Content><StatusTimeline events={session.registration.status_events} /></Card.Content>
	</Card.Root>
</div>
