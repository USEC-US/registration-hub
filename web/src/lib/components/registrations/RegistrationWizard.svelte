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
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import type { PublicTournament, PublicTournamentGame } from '$lib/api/types';
	let { data }: { data: { tournament: PublicTournament; game: PublicTournamentGame } } = $props();
	const divisionId = untrack(() => data.game.id);
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
	const teamRequired = $derived(data.game.main_roster_size + data.game.substitute_limit > 1);
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
	const available = $derived(
		data.game.is_registration_open &&
			(data.game.capacity_remaining === null || data.game.capacity_remaining > 0) &&
			(Number(data.game.fee_amount) === 0 || data.game.payment_available)
	);
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
			members.filter((x) => x.roster_role === 'main').length === data.game.main_roster_size &&
			members.filter((x) => x.roster_role === 'substitute').length <= data.game.substitute_limit &&
			members.filter((x) => x.is_captain).length === 1 &&
			(!members[0] || submitterRole === 'manager' || members[0].is_captain) &&
			members.every(
				(x) =>
					x.gamer_tag_snapshot.trim() &&
					x.first_name_snapshot.trim() &&
					x.last_name_snapshot.trim() &&
					/^\d{4}-\d{2}-\d{2}$/.test(x.date_of_birth_snapshot) &&
					x.date_of_birth_snapshot <= new Date().toISOString().slice(0, 10) &&
					(!data.tournament.students_only || x.student_id_snapshot.trim()) &&
					(x.institution_id || x.institution_label?.trim())
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
				currentActorId: authState.currentUser?.id ?? null,
				accessToken,
				turnstileToken: turnstileToken || null
			});
			turnstileWidget?.reset();
			await report(await request);
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
		if (submitting || !context) return;
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
			await report(await request);
		} finally {
			if (active) submitting = false;
		}
	}
	function formatFee() {
		return new Intl.NumberFormat(getLocale(), {
			style: 'currency',
			currency: data.game.fee_currency
		}).format(Number(data.game.fee_amount));
	}
</script>

<svelte:head
	><title>{m.registration_form_heading({ game: data.game.game_name })} · {m.app_title()}</title
	></svelte:head
>
<header class="mb-8">
	<a class="underline" href={resolve(localizeInternalHref(`/tournaments/${data.tournament.slug}`))}
		>{m.registration_back_to_tournament()}</a
	>
	<h1 class="mt-4 font-heading text-3xl font-semibold">
		{m.registration_form_heading({ game: data.game.game_name })}
	</h1>
	<p class="mt-3">{m.registration_form_intro({ tournament: data.tournament.name })}</p>
</header>
{#if loading}<p role="status">{m.registration_loading()}</p>{:else}
	{#if warning}<Alert.Root class="mb-4"
			><Alert.Description>{m.stages_storage()}</Alert.Description></Alert.Root
		>{/if}
	<SavedRegistrationChoices {entries} onrecover={recover} onforget={forget} />
	{#if confirmation}<h2>{m.registration_confirmed_heading()}</h2>
		<p>{m.registration_reference({ id: confirmation.id })}</p>
		<p>{m.registration_corrections()}</p>
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
	{:else if !available}<p role="status">{m.stages_closed()}</p>
	{:else}
		{#if !accessToken}<Alert.Root role="note" class="mb-6"
				><Alert.Title>{m.registration_account_benefits_title()}</Alert.Title><Alert.Description
					>{m.registration_account_benefits_description()}</Alert.Description
				>
				<div class="flex flex-wrap gap-3">
					<Button href={`${resolve(localizeInternalHref('/auth/register'))}?redirect=${returnTo}`}
						>{m.action_create_account()}</Button
					><Button
						variant="outline"
						href={`${resolve(localizeInternalHref('/auth/sign-in'))}?redirect=${returnTo}`}
						>{m.nav_sign_in()}</Button
					>
				</div></Alert.Root
			>{/if}
		<RegistrationSteps {stage} completed={allowed} onnavigate={navigate} />
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
				{:else if stage === 'roster'}<RosterEditor
						mainRosterSize={data.game.main_roster_size}
						substituteLimit={data.game.substitute_limit}
						studentsOnly={data.tournament.students_only}
						{submitterRole}
						errors={fieldErrors.members}
						bind:members
						bind:institutionLabels
					/>
				{:else}<RegistrationReviewStep
						fields={payload}
						{institutionLabels}
						fee={formatFee()}
						holdMinutes={data.game.payment_hold_minutes}
					/><TurnstileWidget
						bind:this={turnstileWidget}
						bind:token={turnstileToken}
						action="registration-submit"
					/>{/if}
				<div class="flex flex-wrap justify-between gap-3">
					{#if stage !== 'details'}<Button
							type="button"
							variant="outline"
							onclick={() => navigate(stage === 'review' ? 'roster' : 'details')}
							>{m.stages_back()}</Button
						>{/if}<Button type="submit" disabled={submitting}
						>{submitting
							? m.registration_submitting()
							: stage === 'review'
								? m.action_submit_registration()
								: m.stages_continue()}</Button
					>
				</div>
			{/if}
		</form>
		{#if saved}<p role="status" class="mt-4 text-sm">{m.stages_saved()}</p>{/if}<Button
			variant="ghost"
			class="mt-3"
			onclick={clearProgress}>{m.stages_clear()}</Button
		>
	{/if}{/if}
