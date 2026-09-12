<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { ApiRequestError } from '$lib/api/client';
	import { submitRegistration } from '$lib/api/registrations';
	import type { RegistrationMemberInput, RegistrationRead, SubmitterRole } from '$lib/api/types';
	import { clearSession, getAccessToken } from '$lib/auth/session';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import Field from '$lib/components/forms/Field.svelte';
	import TurnstileWidget from '$lib/components/forms/TurnstileWidget.svelte';
	import RosterEditor from '$lib/components/registrations/RosterEditor.svelte';
	import PaymentProofField from '$lib/components/registrations/PaymentProofField.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Card from '$lib/components/ui/card';
	import * as FormField from '$lib/components/ui/field';
	import * as RadioGroup from '$lib/components/ui/radio-group';
	import * as Alert from '$lib/components/ui/alert';
	import { Spinner } from '$lib/components/ui/spinner';
	import { Badge } from '$lib/components/ui/badge';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import UserRound from '@lucide/svelte/icons/user-round';
	import ClipboardList from '@lucide/svelte/icons/clipboard-list';
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let accessToken = $state<string | null>(null);
	let members = $state<RegistrationMemberInput[]>([]);
	let teamName = $state('');
	let turnstileToken = $state('');
	let turnstileWidget = $state<{ reset: () => void } | null>(null);
	let loading = $state(true);
	let submitterRole = $state<SubmitterRole>('captain');
	let managerName = $state('');
	let facebook = $state('');
	let phone = $state('');
	let email = $state('');
	let discord = $state('');
	let reference = $state('');
	let proofFile = $state<File | undefined>();
	let proofSelectionError = $state('');
	let confirmation = $state<RegistrationRead | null>(null);
	const paymentRequired = $derived(Number(data.game.fee_amount) > 0);
	let submitting = $state(false);
	let fieldErrors = $state<Record<string, string[]>>({});
	let formErrors = $state<string[]>([]);

	function formatFee(): string {
		return new Intl.NumberFormat(getLocale(), {
			style: 'currency',
			currency: data.game.fee_currency
		}).format(Number(data.game.fee_amount));
	}

	onMount(() => {
		accessToken = getAccessToken();

		loading = false;
	});

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting || loading || confirmation || proofSelectionError) return;
		fieldErrors = {};
		formErrors = [];
		if (!facebook.trim())
			fieldErrors.contact_facebook_snapshot = [m.registration_contact_required()];
		if (!phone.trim()) fieldErrors.contact_phone_snapshot = [m.registration_contact_required()];
		if (submitterRole === 'manager' && !managerName.trim())
			fieldErrors.manager_name_snapshot = [m.registration_manager_required()];
		if (members.some((member) => !member.institution_id && !member.institution_label?.trim()))
			fieldErrors.members = [m.registration_institution_required()];
		if (Object.keys(fieldErrors).length) return;
		if (paymentRequired && !accessToken && !proofFile) {
			fieldErrors.proof_file = [m.payment_evidence_required()];
			return;
		}
		if (
			proofFile &&
			(proofFile.size > 10 * 1024 * 1024 ||
				!['image/jpeg', 'image/png', 'image/webp'].includes(proofFile.type))
		) {
			fieldErrors.proof_file = [m.payment_image_invalid()];
			return;
		}
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
					team_name: data.game.main_roster_size + data.game.substitute_limit > 1 ? teamName : '',
					submitter_role: submitterRole,
					manager_name_snapshot: submitterRole === 'manager' ? managerName : '',
					contact_facebook_snapshot: facebook,
					contact_phone_snapshot: phone,
					contact_email_snapshot: email,
					contact_discord_snapshot: discord,
					members
				},
				turnstileToken,
				proofFile,
				reference
			);
			turnstileWidget?.reset();
			const registration = await request;
			if (accessToken)
				await goto(resolve(localizeInternalHref(`/account/registrations/${registration.id}`)));
			else confirmation = registration;
		} catch (cause) {
			if (cause instanceof ApiRequestError && cause.status === 401 && accessToken) {
				clearSession();
				accessToken = null;
				formErrors = [m.registration_session_expired()];
				return;
			}
			const nextErrors = formErrorsFrom(cause, m.registration_submit_failed());
			fieldErrors = nextErrors.fieldErrors;
			formErrors = [
				...nextErrors.formErrors,
				...Object.entries(nextErrors.fieldErrors).flatMap(([field, errors]) =>
					[
						'team_name',
						'members',
						'contact_facebook_snapshot',
						'contact_phone_snapshot',
						'contact_email_snapshot',
						'contact_discord_snapshot',
						'manager_name_snapshot',
						'proof_file',
						'reference'
					].includes(field)
						? []
						: errors
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

<header class="mb-8 flex flex-col gap-5">
	<a
		class="inline-flex w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
		href={resolve(localizeInternalHref(`/tournaments/${data.tournament.slug}`))}
	>
		<ArrowLeft class="size-4" aria-hidden="true" />{m.registration_back_to_tournament()}
	</a>
	<div class="flex flex-wrap items-end justify-between gap-5">
		<div>
			<p class="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
				{data.tournament.name}
			</p>
			<h1 class="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
				{m.registration_form_heading({ game: data.game.game_name })}
			</h1>
			<p class="mt-3 max-w-2xl text-base text-muted-foreground">
				{m.registration_form_intro({ tournament: data.tournament.name })}
			</p>
		</div>
		{#if data.tournament.students_only}<Badge variant="secondary"
				>{m.tournament_students_only()}</Badge
			>{/if}
	</div>
	<div class="flex flex-wrap gap-x-6 gap-y-2 border-y py-3 text-sm lg:hidden">
		<span
			>{m.game_roster_summary({
				main: data.game.main_roster_size,
				substitutes: data.game.substitute_limit
			})}</span
		>
		<span class="font-medium">{m.game_fee()}: {formatFee()}</span>
	</div>
</header>

{#if loading}
	<p role="status" class="mt-8">{m.registration_loading()}</p>
{:else if confirmation}
	<Card.Root class="mt-8 rounded-xl py-6" data-registration-confirmation>
		<Card.Header>
			<Card.Title role="heading" aria-level={2}>{m.registration_confirmed_heading()}</Card.Title>
			<Card.Description>{m.registration_reference({ id: confirmation.id })}</Card.Description>
		</Card.Header>
		<Card.Content class="flex flex-col gap-3">
			<p>
				{data.tournament.name} · {data.game.game_name}{confirmation.team_name
					? ` · ${confirmation.team_name}`
					: ''}
			</p>
			<p>{m.registration_corrections()}</p>
			<a class="underline" href="https://facebook.com/hcmusec"
				>{m.registration_contact_organizers()}</a
			>
		</Card.Content>
	</Card.Root>
{:else}
	<div class="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_17rem] xl:gap-10">
		<form class="registration-form min-w-0" aria-busy={submitting} onsubmit={handleSubmit}>
			<div class="flex flex-col gap-6">
				<ErrorSummary errors={formErrors} />
				{#if !accessToken}
					<Alert.Root class="rounded-lg">
						<UserRound aria-hidden="true" />
						<Alert.Description>
							{m.registration_account_benefits()}
							<a
								class="font-medium underline underline-offset-4"
								href={resolve(
									localizeInternalHref(
										`/auth/sign-in?redirect=${encodeURIComponent(`${page.url.pathname}${page.url.search}${page.url.hash}`)}`
									)
								)}>{m.nav_sign_in()}</a
							>
						</Alert.Description>
					</Alert.Root>
				{/if}
				<Card.Root class="gap-6 rounded-xl py-6" aria-labelledby="registration-details-heading">
					<Card.Header>
						<div class="flex items-start gap-3">
							<span
								class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono-data text-sm font-semibold text-primary"
								aria-hidden="true">01</span
							>
							<div class="flex flex-col gap-1">
								<Card.Title
									><h2 id="registration-details-heading">
										{m.registration_details_heading()}
									</h2></Card.Title
								>
								<Card.Description>{m.registration_details_intro()}</Card.Description>
							</div>
						</div>
					</Card.Header>
					<Card.Content class="flex flex-col gap-6">
						<FormField.Set>
							<FormField.Legend>{m.registration_role_heading()}</FormField.Legend>
							<RadioGroup.Root
								bind:value={submitterRole}
								aria-label={m.registration_role_heading()}
								class="grid gap-3 sm:grid-cols-2"
							>
								<FormField.Label
									class="w-full cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors hover:bg-muted/50"
								>
									<RadioGroup.Item
										value="captain"
										aria-label={m.registration_role_captain()}
										class="mt-1 shrink-0"
									/>
									<span class="flex flex-col gap-1.5">
										<span class="flex items-center gap-2 font-semibold"
											><UserRound
												class="size-4"
												aria-hidden="true"
											/>{m.registration_role_captain()}</span
										>
										<span class="text-sm font-normal text-muted-foreground"
											>{m.registration_captain_hint()}</span
										>
									</span>
								</FormField.Label>
								<FormField.Label
									class="w-full cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors hover:bg-muted/50"
								>
									<RadioGroup.Item
										value="manager"
										aria-label={m.registration_role_manager()}
										class="mt-1 shrink-0"
									/>
									<span class="flex flex-col gap-1.5">
										<span class="flex items-center gap-2 font-semibold"
											><ClipboardList
												class="size-4"
												aria-hidden="true"
											/>{m.registration_role_manager()}</span
										>
										<span class="text-sm font-normal text-muted-foreground"
											>{m.registration_manager_hint()}</span
										>
									</span>
								</FormField.Label>
							</RadioGroup.Root>
						</FormField.Set>
						{#if data.game.main_roster_size + data.game.substitute_limit > 1}
							<div class="border-t pt-6">
								<Field
									label={m.field_team_name()}
									name="team_name"
									required
									maxlength={100}
									error={fieldErrors.team_name?.[0]}
									bind:value={teamName}
								/>
							</div>
						{/if}
						<FormField.Set class="border-t pt-6">
							<FormField.Legend>{m.registration_contact_heading()}</FormField.Legend>
							<FormField.Description class="flex items-start gap-2"
								><ShieldCheck
									class="mt-0.5 size-4 shrink-0"
									aria-hidden="true"
								/>{m.registration_contact_private()}</FormField.Description
							>
							<FormField.Group class="sm:grid sm:grid-cols-2">
								{#if submitterRole === 'manager'}<Field
										label={m.registration_manager_name()}
										name="manager_name_snapshot"
										required
										maxlength={100}
										error={fieldErrors.manager_name_snapshot?.[0]}
										bind:value={managerName}
									/>{/if}
								<Field
									label={m.registration_facebook()}
									name="contact_facebook_snapshot"
									required
									maxlength={255}
									error={fieldErrors.contact_facebook_snapshot?.[0]}
									bind:value={facebook}
								/>
								<Field
									label={m.registration_phone()}
									name="contact_phone_snapshot"
									type="tel"
									required
									maxlength={32}
									error={fieldErrors.contact_phone_snapshot?.[0]}
									bind:value={phone}
								/>
								<Field
									label={m.registration_email()}
									name="contact_email_snapshot"
									type="email"
									maxlength={254}
									error={fieldErrors.contact_email_snapshot?.[0]}
									bind:value={email}
								/>
								<Field
									label={m.registration_discord()}
									name="contact_discord_snapshot"
									maxlength={100}
									error={fieldErrors.contact_discord_snapshot?.[0]}
									bind:value={discord}
								/>
							</FormField.Group>
						</FormField.Set>
					</Card.Content>
				</Card.Root>
				<Card.Root class="gap-0 rounded-xl py-6">
					<Card.Content>
						<RosterEditor
							mainRosterSize={data.game.main_roster_size}
							substituteLimit={data.game.substitute_limit}
							studentsOnly={data.tournament.students_only}
							{submitterRole}
							errors={fieldErrors.members}
							bind:members
						/></Card.Content
					>
				</Card.Root>
				<Card.Root class="gap-6 rounded-xl pt-6" aria-labelledby="registration-submit-heading">
					<Card.Header>
						<div class="flex items-start gap-3">
							<span
								class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono-data text-sm font-semibold text-primary"
								aria-hidden="true">03</span
							>
							<div class="flex flex-col gap-1">
								<Card.Title
									><h2 id="registration-submit-heading">
										{paymentRequired
											? m.registration_payment_and_submit()
											: m.registration_ready_to_submit()}
									</h2></Card.Title
								>
								<Card.Description>{m.registration_corrections()}</Card.Description>
							</div>
						</div>
					</Card.Header>
					<Card.Content class="flex flex-col gap-6">
						{#if paymentRequired}
							<FormField.Set>
								<FormField.Legend>{m.payment_attempt_heading()}</FormField.Legend>
								<FormField.Description
									>{accessToken
										? m.registration_proof_account()
										: m.registration_proof_guest()}</FormField.Description
								>
								<FormField.Group>
									<PaymentProofField
										required={!accessToken}
										disabled={submitting}
										error={fieldErrors.proof_file?.[0]}
										bind:file={proofFile}
										bind:selectionError={proofSelectionError}
									/>
									<Field
										label={m.field_payment_reference()}
										name="reference"
										maxlength={128}
										error={fieldErrors.reference?.[0]}
										bind:value={reference}
									/>
								</FormField.Group>
							</FormField.Set>
						{/if}
						<TurnstileWidget
							bind:this={turnstileWidget}
							action="registration-submit"
							bind:token={turnstileToken}
						/>
					</Card.Content>
					<Card.Footer
						class="flex-col items-stretch gap-4 border-t pt-6 sm:flex-row sm:items-center sm:justify-between"
					>
						<div>
							<p class="text-xs text-muted-foreground">{m.game_fee()}</p>
							<p class="font-mono-data mt-1 text-lg font-semibold">{formatFee()}</p>
						</div>
						<Button class="min-h-11 w-full sm:w-auto" type="submit" disabled={submitting}>
							{#if submitting}<Spinner aria-hidden="true" />{/if}
							{submitting ? m.registration_submitting() : m.action_submit_registration()}
						</Button>
					</Card.Footer>
				</Card.Root>
			</div>
		</form>
		<aside class="sticky top-6 hidden lg:block" aria-labelledby="registration-overview-heading">
			<Card.Root class="gap-5 rounded-xl pt-6">
				<Card.Header>
					<Card.Title
						><h2 id="registration-overview-heading">
							{m.registration_overview_heading()}
						</h2></Card.Title
					>
					<Card.Description>{data.tournament.name}</Card.Description>
				</Card.Header>
				<Card.Content>
					<dl class="flex flex-col gap-4 text-sm">
						<div class="flex items-start justify-between gap-4">
							<dt class="text-muted-foreground">{m.registration_game_label()}</dt>
							<dd class="text-right font-medium">{data.game.game_name}</dd>
						</div>
						<div class="flex items-start justify-between gap-4">
							<dt class="text-muted-foreground">{m.registration_main_count_label()}</dt>
							<dd class="font-mono-data font-medium">{data.game.main_roster_size}</dd>
						</div>
						<div class="flex items-start justify-between gap-4">
							<dt class="text-muted-foreground">{m.registration_substitute_count_label()}</dt>
							<dd class="font-mono-data font-medium">{data.game.substitute_limit}</dd>
						</div>
						<div class="flex items-start justify-between gap-4 border-t pt-4">
							<dt class="text-muted-foreground">{m.game_fee()}</dt>
							<dd class="font-mono-data font-semibold">{formatFee()}</dd>
						</div>
					</dl>
				</Card.Content>
				<Card.Footer class="border-t pt-5">
					<p class="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
						<ShieldCheck
							class="mt-0.5 size-4 shrink-0"
							aria-hidden="true"
						/>{m.roster_identity_private()}
					</p>
				</Card.Footer>
			</Card.Root>
		</aside>
	</div>
{/if}
