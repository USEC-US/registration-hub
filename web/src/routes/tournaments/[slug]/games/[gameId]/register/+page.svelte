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
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale } from '$lib/paraglide/runtime';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Card from '$lib/components/ui/card';
	import * as FormField from '$lib/components/ui/field';
	import * as RadioGroup from '$lib/components/ui/radio-group';
	import * as Alert from '$lib/components/ui/alert';
	import { Input } from '$lib/components/ui/input';
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
	let submitterRole = $state<SubmitterRole>('captain');
	let managerName = $state('');
	let facebook = $state('');
	let phone = $state('');
	let email = $state('');
	let discord = $state('');
	let reference = $state('');
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
		if (submitting || loading || confirmation) return;
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
		const formData = new FormData(event.currentTarget as HTMLFormElement);
		const file = formData.get('proof_file');
		const proofFile = file instanceof File && file.size > 0 ? file : undefined;
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

{#if loading}
	<p role="status" class="mt-8">{m.registration_loading()}</p>
{:else if confirmation}
	<Card.Root class="mt-8" data-registration-confirmation>
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
	<form class="mt-8" aria-busy={submitting} onsubmit={handleSubmit}>
		<Card.Root class="gap-8">
			<Card.Content class="grid gap-8">
				<ErrorSummary errors={formErrors} />
				{#if !accessToken}
					<Alert.Root
						><Alert.Description
							>{m.registration_account_benefits()}
							<a
								class="underline"
								href={resolve(
									localizeInternalHref(
										`/auth/sign-in?redirect=${encodeURIComponent(`${page.url.pathname}${page.url.search}${page.url.hash}`)}`
									)
								)}>{m.nav_sign_in()}</a
							></Alert.Description
						></Alert.Root
					>
				{/if}
				<FormField.Set>
					<FormField.Legend>{m.registration_role_heading()}</FormField.Legend>
					<RadioGroup.Root
						bind:value={submitterRole}
						aria-label={m.registration_role_heading()}
						class="flex flex-wrap gap-6"
					>
						<FormField.Label class="flex items-center gap-2"
							><RadioGroup.Item
								value="captain"
								aria-label={m.registration_role_captain()}
							/>{m.registration_role_captain()}</FormField.Label
						>
						<FormField.Label class="flex items-center gap-2"
							><RadioGroup.Item
								value="manager"
								aria-label={m.registration_role_manager()}
							/>{m.registration_role_manager()}</FormField.Label
						>
					</RadioGroup.Root>
					<FormField.Description
						>{submitterRole === 'captain'
							? m.registration_captain_hint()
							: m.registration_manager_hint()}</FormField.Description
					>
				</FormField.Set>
				<FormField.Set>
					<FormField.Legend>{m.registration_contact_heading()}</FormField.Legend>
					<FormField.Description>{m.registration_contact_private()}</FormField.Description>
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
				{#if data.game.main_roster_size + data.game.substitute_limit > 1}
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
					mainRosterSize={data.game.main_roster_size}
					substituteLimit={data.game.substitute_limit}
					studentsOnly={data.tournament.students_only}
					{submitterRole}
					errors={fieldErrors.members}
					bind:members
				/>
				{#if paymentRequired}
					<FormField.Set>
						<FormField.Legend>{m.payment_attempt_heading()}</FormField.Legend>
						<FormField.Description
							>{accessToken
								? m.registration_proof_account()
								: m.registration_proof_guest()}</FormField.Description
						>
						<FormField.Group>
							<FormField.Field data-invalid={!!fieldErrors.proof_file}>
								<FormField.Label for="proof_file">{m.field_payment_proof()}</FormField.Label>
								<Input
									id="proof_file"
									name="proof_file"
									type="file"
									accept="image/jpeg,image/png,image/webp"
									aria-required={!accessToken}
									aria-invalid={!!fieldErrors.proof_file}
									aria-describedby="payment-image-hint proof-error"
								/>
								<FormField.Description id="payment-image-hint"
									>{m.payment_image_hint()}</FormField.Description
								>
								{#if fieldErrors.proof_file}<p
										id="proof-error"
										role="alert"
										class="text-sm text-destructive"
									>
										{fieldErrors.proof_file[0]}
									</p>{/if}
							</FormField.Field>
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
				<p class="text-sm text-muted-foreground">{m.registration_corrections()}</p>
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
{/if}
