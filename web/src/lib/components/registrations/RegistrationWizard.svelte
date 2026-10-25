<script lang="ts">
	import { beforeNavigate, goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { onMount, tick, untrack } from 'svelte';
	import type {
		RegistrationRead,
		RegistrationSubmissionPayload,
		SubmitterRole,
		RegistrationMemberInput
	} from '$lib/api/types';
	import { getAccessToken } from '$lib/auth/session';
	import { authState } from '$lib/states/auth-state.svelte';
	import {
		getRegistrationStorage,
		readDraft,
		writeDraft,
		clearDraft,
		listAccess,
		forgetAccess,
		type DraftStage,
		type RegistrationDraft,
		type SavedRegistrationAccess,
		type PendingSavedRegistrationAccess
	} from '$lib/registrations/browser-storage';
	import {
		submitRegistrationAttempt,
		recoverRegistrationAttempt,
		type RegistrationSubmissionResult
	} from '$lib/registrations/submission';
	import RegistrationDetailsStep from '$lib/components/registrations/RegistrationDetailsStep.svelte';
	import RegistrationReviewStep from '$lib/components/registrations/RegistrationReviewStep.svelte';
	import RegistrationSteps from '$lib/components/registrations/RegistrationSteps.svelte';
	import SavedRegistrationChoices from '$lib/components/registrations/SavedRegistrationChoices.svelte';
	import RosterEditor from '$lib/components/registrations/RosterEditor.svelte';
	import TurnstileWidget from '$lib/components/forms/TurnstileWidget.svelte';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Alert from '$lib/components/ui/alert';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Separator } from '$lib/components/ui/separator';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Spinner } from '$lib/components/ui/spinner';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import Check from '@lucide/svelte/icons/check';
	import Gamepad2 from '@lucide/svelte/icons/gamepad-2';
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	import UserRound from '@lucide/svelte/icons/user-round';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import type { PublicTournament, PublicTournamentGame } from '$lib/api/types';
	let { data }: { data: { tournament: PublicTournament; game: PublicTournamentGame } } = $props();
	// The keyed instance owns these rules through its final departure flush, even if incoming props change first.
	const instanceData = untrack(() => ({
		tournament: structuredClone($state.snapshot(data.tournament)),
		game: structuredClone($state.snapshot(data.game))
	}));
	const divisionId = instanceData.game.id;
	let active = true;
	let stage = $state<DraftStage>('details');
	let teamName = $state(''),
		teamTag = $state(''),
		managerName = $state(''),
		facebook = $state(''),
		phone = $state(''),
		email = $state(''),
		discord = $state('');
	let submitterRole = $state<SubmitterRole>('captain');
	let members = $state<RegistrationMemberInput[]>([]);
	let institutionLabels = $state<Record<string, string>>({});
	let loading = $state(true),
		submitting = $state(false),
		warning = $state(false),
		saved = $state(false);
	let accessToken = $state<string | null>(null);
	const legacyKey = `usec-payment-intent:${divisionId}`;
	let legacyToken = $state<string | null>(null);
	let legacyUnpaid = $state(false);
	const legacyBlocked = $derived(Boolean(legacyToken) && !legacyUnpaid);
	// This association is intentionally not a persisted unpaid declaration.
	let legacyFreshCredential: string | null = null;
	let context: ReturnType<typeof getRegistrationStorage> | undefined;
	let restore = $state<RegistrationDraft | null>(null);
	let entries = $state<SavedRegistrationAccess[]>([]);
	let pending = $state<PendingSavedRegistrationAccess | null>(null);
	let confirmation = $state<RegistrationRead | null>(null);
	let turnstileToken = $state('');
	let turnstileWidget = $state<{ reset: () => void } | null>(null);
	let formErrors = $state<string[]>([]),
		fieldErrors = $state<Record<string, string[]>>({});
	let form = $state<HTMLFormElement>();
	let focusRegion = $state<HTMLDivElement>();
	let dirty = false,
		finished = false,
		savingEnabled = false;
	let timer: ReturnType<typeof setTimeout> | undefined;
	const teamRequired = $derived(
		instanceData.game.main_roster_size + instanceData.game.substitute_limit > 1
	);
	const payload = $derived<RegistrationSubmissionPayload>({
		tournament_game: divisionId,
		team_name: teamRequired ? teamName : '',
		team_tag: teamRequired ? teamTag : '',
		submitter_role: submitterRole,
		manager_name_snapshot: submitterRole === 'manager' ? managerName : '',
		contact_facebook_snapshot: facebook,
		contact_phone_snapshot: phone,
		contact_email_snapshot: email,
		contact_discord_snapshot: discord,
		members
	});
	const allowed = $derived<DraftStage[]>(
		detailsValid()
			? rosterValid()
				? ['details', 'roster', 'review']
				: ['details', 'roster']
			: ['details']
	);
	const unavailableMessage = $derived.by(() => {
		const game = instanceData.game;
		if (game.registration_state === 'not_open') return m.stages_not_open();
		if (game.registration_state === 'closed') return m.stages_registration_closed();
		if (
			game.registration_state === 'full' ||
			(game.capacity_remaining !== null && game.capacity_remaining <= 0)
		)
			return m.stages_full();
		if (!game.is_registration_open) return m.stages_closed();
		if (Number(game.fee_amount) !== 0 && !game.payment_available)
			return m.stages_payment_unavailable();
		return '';
	});
	const available = $derived(!unavailableMessage);
	const returnTo = $derived(
		encodeURIComponent(`${page.url.pathname}${page.url.search}${page.url.hash}`)
	);
	function detailsValid() {
		return Boolean(
			facebook.trim() &&
			phone.trim() &&
			(!teamRequired || (teamName.trim() && /^[A-Za-z0-9]{2,5}$/.test(teamTag))) &&
			(submitterRole !== 'manager' || managerName.trim()) &&
			(!email || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
		);
	}
	function rosterValid() {
		return (
			members.filter((x) => x.roster_role === 'main').length ===
				instanceData.game.main_roster_size &&
			members.filter((x) => x.roster_role === 'substitute').length <=
				instanceData.game.substitute_limit &&
			members.filter((x) => x.is_captain).length === 1 &&
			(!members[0] || submitterRole === 'manager' || members[0].is_captain) &&
			members.every(
				(x) =>
					x.gamer_tag_snapshot.trim() &&
					x.first_name_snapshot.trim() &&
					x.last_name_snapshot.trim() &&
					/^\d{4}-\d{2}-\d{2}$/.test(x.date_of_birth_snapshot) &&
					x.date_of_birth_snapshot <= new Date().toISOString().slice(0, 10) &&
					(!instanceData.tournament.students_only ||
						(x.student_id_snapshot.trim() && (x.institution_id || x.institution_label?.trim())))
			)
		);
	}
	function refreshStorage() {
		if (context) {
			entries = listAccess(context.storage, divisionId);
			warning = Boolean(context.persistenceWarning) || warning;
		}
	}
	function flush() {
		if (timer) clearTimeout(timer);
		if (!context || !savingEnabled || !dirty || restore || finished || pending) return;
		writeDraft(context.storage, {
			version: 1,
			gameId: divisionId,
			updatedAt: Date.now(),
			stage,
			fields: $state.snapshot(payload),
			institutionLabels: $state.snapshot(institutionLabels)
		});
		dirty = false;
		saved = true;
		refreshStorage();
	}
	function edited() {
		if (!active || !savingEnabled || restore || finished) return;
		dirty = true;
		if (timer) clearTimeout(timer);
		timer = setTimeout(flush, 300);
	}
	$effect(() => {
		JSON.stringify(payload);
		JSON.stringify(institutionLabels);
		void stage;
		untrack(edited);
	});
	beforeNavigate(() => flush());
	function restoreDraft() {
		if (!restore) return;
		const f = restore.fields;
		teamName = f.team_name ?? '';
		teamTag = f.team_tag ?? '';
		submitterRole = f.submitter_role;
		managerName = f.manager_name_snapshot ?? '';
		facebook = f.contact_facebook_snapshot;
		phone = f.contact_phone_snapshot;
		email = f.contact_email_snapshot ?? '';
		discord = f.contact_discord_snapshot ?? '';
		members = f.members;
		institutionLabels = restore.institutionLabels;
		stage = restore.stage;
		restore = null;
		savingEnabled = true;
		stage = allowed.includes(stage) ? stage : allowed.at(-1)!;
		void navigate(stage, true);
	}
	function discard() {
		if (context) clearDraft(context.storage, divisionId);
		restore = null;
		savingEnabled = true;
		saved = false;
		dirty = false;
		refreshStorage();
	}
	function clearProgress() {
		if (timer) clearTimeout(timer);
		if (context) clearDraft(context.storage, divisionId);
		dirty = false;
		saved = false;
		refreshStorage();
	}
	async function navigate(next: DraftStage, replace = false) {
		if (!active) return;
		if (!allowed.includes(next)) next = allowed.at(-1)!;
		stage = next;
		formErrors = [];
		const url = new URL(page.url);
		url.searchParams.set('step', next);
		await goto(resolve(localizeInternalHref(`${url.pathname}${url.search}${url.hash}`)), {
			replaceState: replace,
			keepFocus: true,
			noScroll: true
		});
		await tick();
		if (!active) return;
		const heading = form?.querySelector<HTMLElement>('h2');
		if (heading) {
			heading.tabIndex = -1;
			heading.focus();
		}
	}
	let lastHandledUrl = '';
	$effect(() => {
		const href = page.url.href;
		if (loading || href === lastHandledUrl) return;
		lastHandledUrl = href;
		const requested = page.url.searchParams.get('step');
		if (!loading && !restore) {
			untrack(() => {
				const next = allowed.includes(requested as DraftStage)
					? (requested as DraftStage)
					: 'details';
				if (stage !== next) stage = next;
				if (requested && requested !== next) {
					const url = new URL(page.url);
					url.searchParams.set('step', next);
					void goto(resolve(localizeInternalHref(`${url.pathname}${url.search}${url.hash}`)), {
						replaceState: true,
						keepFocus: true,
						noScroll: true
					});
				}
				void tick().then(() => {
					if (!active) return;
					const heading = form?.querySelector<HTMLElement>('h2');
					if (heading) {
						heading.tabIndex = -1;
						heading.focus();
					}
				});
			});
		}
	});
	onMount(() => {
		try {
			legacyToken = sessionStorage.getItem(legacyKey);
		} catch {
			warning = true;
		}
		context = getRegistrationStorage();
		restore = readDraft(context.storage, divisionId, Date.now());
		refreshStorage();
		savingEnabled = !restore;
		try {
			accessToken = getAccessToken();
		} catch {
			warning = true;
		}
		void (async () => {
			try {
				if (accessToken) await authState.initialize();
			} catch {
				warning = true;
			}
			if (active) loading = false;
		})();
		const hide = () => flush();
		window.addEventListener('pagehide', hide);
		document.addEventListener('visibilitychange', hide);
		return () => {
			flush();
			active = false;
			savingEnabled = false;
			window.removeEventListener('pagehide', hide);
			document.removeEventListener('visibilitychange', hide);
			if (timer) clearTimeout(timer);
		};
	});
	async function report(result: RegistrationSubmissionResult) {
		// Even a late success belongs to its original division. Never erase a newer
		// token or an old quote merely because an unrelated saved entry resumed.
		if (
			result.status === 'submitted' &&
			legacyToken &&
			result.credential === legacyFreshCredential
		) {
			try {
				if (sessionStorage.getItem(legacyKey) === legacyToken) sessionStorage.removeItem(legacyKey);
			} catch {
				// Conservative retention is safe when browser storage becomes unavailable.
			}
		}
		if (!active) return;
		refreshStorage();
		if (result.status === 'submitted') {
			finished = true;
			dirty = false;
			if (timer) clearTimeout(timer);
			const registration = result.registration ?? result.session.registration;
			pending = null;
			if (registration.payment_required)
				await goto(resolve(localizeInternalHref(`/registrations/${registration.id}/payment`)));
			else confirmation = registration;
			return;
		}
		pending =
			entries.find(
				(entry): entry is PendingSavedRegistrationAccess =>
					entry.credential === result.credential && entry.attemptState !== 'submitted'
			) ?? null;
		if (result.status === 'editable') {
			const errors = formErrorsFrom(result.error, m.registration_submit_failed());
			fieldErrors = errors.fieldErrors;
			const target = Object.keys(fieldErrors).some((k) => k.startsWith('members'))
				? 'roster'
				: 'details';
			await navigate(target);
			if (!active) return;
			formErrors = [...errors.formErrors, ...Object.values(fieldErrors).flat()];
		} else
			formErrors = [
				result.status === 'challenge-required'
					? m.turnstile_required()
					: result.status === 'account-session-required' || result.status === 'actor-required'
						? m.registration_session_expired()
						: m.stages_uncertain()
			];
		await tick();
		if (active) focusRegion?.focus();
	}
	async function recover(entry: SavedRegistrationAccess) {
		if (entry.attemptState === 'submitted' || !context || submitting) return;
		pending = entry;
		submitting = true;
		try {
			try {
				accessToken = getAccessToken();
				if (accessToken) await authState.initialize();
			} catch {
				warning = true;
				accessToken = null;
			}
			if (!active) return;
			const request = recoverRegistrationAttempt({
				storage: context.storage,
				entry,
				allowReplay: !legacyBlocked,
				currentActorId: authState.currentUser?.id ?? null,
				accessToken,
				turnstileToken: turnstileToken || null
			});
			turnstileWidget?.reset();
			const result = await request;
			// A receipt (rather than a resumed session) confirms an explicitly allowed replay.
			if (legacyUnpaid && result.status === 'submitted' && result.registration) {
				legacyFreshCredential = result.credential;
			}
			await report(result);
		} finally {
			if (active) submitting = false;
		}
	}
	function forget(entry: SavedRegistrationAccess) {
		if (context) forgetAccess(context.storage, entry.credential);
		refreshStorage();
	}
	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (submitting || !context || legacyBlocked) return;
		if (pending) {
			await recover(pending);
			return;
		}
		if (!form?.reportValidity()) return;
		if (stage !== 'review') {
			if ((stage === 'details' && !detailsValid()) || (stage === 'roster' && !rosterValid())) {
				formErrors = [stage === 'details' ? m.stages_invalid() : m.stages_roster_invalid()];
				await tick();
				if (active) focusRegion?.focus();
				return;
			}
			await navigate(stage === 'details' ? 'roster' : 'review');
			return;
		}
		if (!detailsValid() || !rosterValid()) {
			await navigate(!detailsValid() ? 'details' : 'roster');
			return;
		}
		if (!turnstileToken) {
			formErrors = [m.turnstile_required()];
			return;
		}
		if (entries.some((e) => e.attemptState !== 'submitted')) {
			formErrors = [m.stages_uncertain()];
			return;
		}
		submitting = true;
		try {
			try {
				accessToken = getAccessToken();
				if (accessToken) await authState.initialize();
			} catch {
				warning = true;
				accessToken = null;
			}
			if (!active) return;
			const request = submitRegistrationAttempt({
				storage: context.storage,
				actorId: authState.currentUser?.id ?? null,
				accessToken,
				payload: $state.snapshot(payload),
				turnstileToken
			});
			turnstileWidget?.reset();
			const result = await request;
			if (legacyUnpaid) legacyFreshCredential = result.credential;
			await report(result);
		} finally {
			if (active) submitting = false;
		}
	}
	function formatFee() {
		return new Intl.NumberFormat(getLocale(), {
			style: 'currency',
			currency: instanceData.game.fee_currency
		}).format(Number(instanceData.game.fee_amount));
	}
</script>

<svelte:head
	><title
		>{m.registration_form_heading({ game: instanceData.game.game_name })} · {m.app_title()}</title
	></svelte:head
>
<div class="mx-auto flex max-w-6xl flex-col gap-7 sm:gap-8">
	<header class="flex flex-col gap-5">
		<a
			class="inline-flex w-fit items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
			href={resolve(localizeInternalHref(`/tournaments/${instanceData.tournament.slug}`))}
		>
			<ArrowLeft class="size-4" aria-hidden="true" />{m.registration_back_to_tournament()}
		</a>
		<div class="flex items-start gap-4">
			<div
				class="hidden size-14 shrink-0 items-center justify-center rounded-2xl border bg-muted/50 sm:flex"
			>
				<Gamepad2 class="size-7 text-primary" aria-hidden="true" />
			</div>
			<div class="flex min-w-0 flex-col gap-2">
				<p class="text-xs font-semibold tracking-wide text-muted-foreground">
					{instanceData.tournament.name}
				</p>
				<h1 class="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
					{m.registration_form_heading({ game: instanceData.game.game_name })}
				</h1>
				<p class="text-sm leading-relaxed text-muted-foreground">
					{m.registration_form_intro({ tournament: instanceData.tournament.name })}
				</p>
			</div>
		</div>
	</header>
	{#if loading}
		<div role="status" class="flex flex-col gap-6">
			<span class="sr-only">{m.registration_loading()}</span><Skeleton
				class="h-28 w-full rounded-xl"
			/><Skeleton class="h-96 w-full rounded-xl" />
		</div>
	{:else}
		{#if warning}<Alert.Root class="mb-4"
				><Alert.Description>{m.stages_storage()}</Alert.Description></Alert.Root
			>{/if}
		<SavedRegistrationChoices {entries} onrecover={recover} onforget={forget} />
		{#if confirmation}<h2>{m.registration_confirmed_heading()}</h2>
			<p>{m.registration_reference({ id: confirmation.id })}</p>
			<p>{m.registration_corrections()}</p>
		{:else if legacyBlocked}<Alert.Root class="mb-6"
				><Alert.Title>{m.stages_legacy_title()}</Alert.Title><Alert.Description
					>{m.stages_legacy_guidance()}</Alert.Description
				>
				<Button
					type="button"
					variant="outline"
					class="h-auto min-h-11 whitespace-normal"
					disabled={submitting}
					onclick={() => {
						legacyUnpaid = true;
					}}>{m.stages_legacy_start_unpaid()}</Button
				></Alert.Root
			>
		{:else if restore}<Alert.Root
				><Alert.Title>{m.stages_restore()}</Alert.Title><Alert.Description
					>{m.stages_saved()}</Alert.Description
				>
				<div class="flex flex-wrap gap-3">
					<Button onclick={restoreDraft}>{m.stages_continue()}</Button><Button
						variant="outline"
						onclick={discard}>{m.stages_discard()}</Button
					>
				</div></Alert.Root
			>
		{:else if !available}<p role="status">{unavailableMessage}</p>
		{:else}
			<RegistrationSteps
				{stage}
				completed={allowed}
				disabled={submitting || Boolean(pending)}
				onnavigate={navigate}
			/>
			<div class="grid min-w-0 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem] xl:gap-8">
				<div class="flex min-w-0 flex-col gap-5">
					<div bind:this={focusRegion} tabindex="-1" aria-live="polite" class="outline-none">
						<ErrorSummary errors={formErrors} />
					</div>
					<form
						bind:this={form}
						onsubmit={handleSubmit}
						class="flex min-w-0 flex-col gap-6"
						aria-busy={submitting}
					>
						{#if pending}<p>{m.stages_uncertain()}</p>
							<TurnstileWidget
								bind:this={turnstileWidget}
								bind:token={turnstileToken}
								action="registration-submit"
							/><Button type="submit" disabled={submitting}>{m.stages_recover()}</Button>
						{:else}
							{#if stage === 'details'}<RegistrationDetailsStep
									{teamRequired}
									{fieldErrors}
									bind:teamName
									bind:teamTag
									bind:submitterRole
									bind:managerName
									bind:facebook
									bind:phone
									bind:email
									bind:discord
								/>
							{:else if stage === 'roster'}<div
									class="rounded-xl border bg-card p-4 shadow-xs sm:p-6"
								>
									<RosterEditor
										mainRosterSize={instanceData.game.main_roster_size}
										substituteLimit={instanceData.game.substitute_limit}
										studentsOnly={instanceData.tournament.students_only}
										{submitterRole}
										errors={fieldErrors.members}
										bind:members
										bind:institutionLabels
									/>
								</div>
							{:else}<RegistrationReviewStep
									fields={payload}
									{institutionLabels}
									fee={formatFee()}
									holdMinutes={instanceData.game.payment_hold_minutes}
								/><TurnstileWidget
									bind:this={turnstileWidget}
									bind:token={turnstileToken}
									action="registration-submit"
								/>{/if}
							<div
								class="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-muted/20 p-4"
							>
								<p class="mr-auto text-xs text-muted-foreground">
									{m.registration_step_progress({
										current: stage === 'details' ? 1 : stage === 'roster' ? 2 : 3,
										total: 3
									})}
								</p>
								{#if stage !== 'details'}<Button
										type="button"
										variant="outline"
										disabled={submitting}
										onclick={() => navigate(stage === 'review' ? 'roster' : 'details')}
										><ArrowLeft
											data-icon="inline-start"
											aria-hidden="true"
										/>{m.stages_back()}</Button
									>{/if}<Button type="submit" disabled={submitting}
									>{#if submitting}<Spinner data-icon="inline-start" />{/if}{submitting
										? m.registration_submitting()
										: stage === 'review'
											? m.action_submit_registration()
											: m.stages_continue()}{#if !submitting}<ArrowRight
											data-icon="inline-end"
											aria-hidden="true"
										/>{/if}</Button
								>
							</div>
						{/if}
					</form>
					<div
						class="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:justify-between"
					>
						{#if saved}<p
								role="status"
								class="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground"
							>
								<Check class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{m.stages_saved()}
							</p>{/if}
						<Button variant="ghost" size="sm" disabled={submitting} onclick={clearProgress}
							>{m.stages_clear()}</Button
						>
					</div>
				</div>
				<aside
					class="flex min-w-0 flex-col gap-5 lg:sticky lg:top-6"
					aria-label={m.registration_summary_heading()}
				>
					<Card.Root class="rounded-xl py-5">
						<Card.Header
							><Card.Title>{m.registration_summary_heading()}</Card.Title><Card.Description
								>{m.registration_summary_intro()}</Card.Description
							></Card.Header
						>
						<Card.Content class="flex flex-col gap-5">
							<div class="flex items-center gap-2">
								<Badge variant="secondary">{instanceData.game.game_name}</Badge
								>{#if instanceData.tournament.students_only}<Badge variant="outline"
										>{m.roster_student_id_required_badge()}</Badge
									>{/if}
							</div>
							<dl class="flex flex-col gap-4">
								<div class="flex flex-col gap-1">
									<dt class="text-xs text-muted-foreground">{m.registration_summary_roster()}</dt>
									<dd class="font-medium">
										{m.game_roster_summary({
											main: instanceData.game.main_roster_size,
											substitutes: instanceData.game.substitute_limit
										})}
									</dd>
								</div>
								<div class="flex items-center justify-between gap-3">
									<dt class="text-xs text-muted-foreground">{m.game_capacity()}</dt>
									<dd class="font-mono-data font-medium">
										{instanceData.game.capacity_remaining ?? m.game_capacity_unlimited()}
									</dd>
								</div>
								<div class="flex items-center justify-between gap-3">
									<dt class="text-xs text-muted-foreground">{m.game_fee()}</dt>
									<dd class="font-mono-data font-semibold">{formatFee()}</dd>
								</div>
							</dl>
							<Separator />
							<p class="text-xs leading-relaxed text-muted-foreground">
								{Number(instanceData.game.fee_amount) === 0
									? m.registration_summary_free()
									: m.registration_summary_payment()}
							</p>
						</Card.Content>
						<Card.Footer class="gap-2 border-t"
							><ShieldCheck class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
							<p class="text-xs leading-relaxed text-muted-foreground">
								{m.registration_contact_private()}
							</p></Card.Footer
						>
					</Card.Root>

					{#if !accessToken}<Alert.Root role="note" class="rounded-xl p-5"
							><UserRound aria-hidden="true" /><Alert.Title
								>{m.registration_account_benefits_title()}</Alert.Title
							><Alert.Description>{m.registration_account_benefits_description()}</Alert.Description
							>
							<div
								class="col-span-full mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2"
							>
								<Button
									href={`${resolve(localizeInternalHref('/auth/register'))}?redirect=${returnTo}`}
									>{m.action_create_account()}</Button
								><Button
									variant="outline"
									href={`${resolve(localizeInternalHref('/auth/sign-in'))}?redirect=${returnTo}`}
									>{m.nav_sign_in()}</Button
								>
							</div></Alert.Root
						>{/if}
					<p class="px-1 text-xs leading-relaxed text-muted-foreground">
						{m.registration_summary_help()}
						<a
							class="underline underline-offset-4 hover:text-foreground"
							href="https://facebook.com/hcmusec">{m.registration_contact_organizers()}</a
						>
					</p>
				</aside>
			</div>
		{/if}
	{/if}
</div>
