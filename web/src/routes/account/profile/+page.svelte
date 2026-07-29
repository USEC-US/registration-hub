<script lang="ts">
	import { updateCurrentUser } from '$lib/api/auth';
	import type { InstitutionChoice } from '$lib/api/types';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import Field from '$lib/components/forms/Field.svelte';
	import InstitutionCombobox from '$lib/components/forms/InstitutionCombobox.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { authState } from '$lib/states/auth-state.svelte';
	import * as m from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Card from '$lib/components/ui/card';
	import * as FormField from '$lib/components/ui/field';
	import { Spinner } from '$lib/components/ui/spinner';
	import { onMount } from 'svelte';

	let firstName = $state('');
	let lastName = $state('');
	let institutionChoice = $state<InstitutionChoice | undefined>(undefined);
	let loading = $state(true);
	let saving = $state(false);
	let saved = $state(false);
	let redirecting = $state(false);
	let fieldErrors = $state<Record<string, string[]>>({});
	let formErrors = $state<string[]>([]);

	onMount(async () => {
		const accessToken = authState.requireAccessToken();
		if (!accessToken) {
			redirecting = true;
			loading = false;
			return;
		}

		const user = await authState.initialize();
		if (!user) {
			if (authState.status === 'signed-out') {
				redirecting = true;
				authState.requireAccessToken();
			} else {
				formErrors = [m.profile_load_failed()];
			}
			loading = false;
			return;
		}

		firstName = user.first_name;
		lastName = user.last_name;
		institutionChoice = user.institution ? { institution_id: user.institution.id } : undefined;
		loading = false;
	});

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (saving) return;

		const session = authState.requireSessionSnapshot();
		if (!session) {
			redirecting = true;
			return;
		}

		saving = true;
		saved = false;
		fieldErrors = {};
		formErrors = [];

		try {
			const institution = institutionChoice ?? { institution_label: '' };
			const user = await updateCurrentUser(session.accessToken, {
				first_name: firstName,
				last_name: lastName,
				...institution
			});
			if (!authState.updateCurrentUser(session, user)) return;

			firstName = user.first_name;
			lastName = user.last_name;
			institutionChoice = user.institution ? { institution_id: user.institution.id } : undefined;
			saved = true;
		} catch (cause) {
			if (!authState.isSessionSnapshotCurrent(session)) return;

			if (authState.handleAuthenticationError(cause)) {
				redirecting = true;
				return;
			}
			({ fieldErrors, formErrors } = formErrorsFrom(cause, m.profile_save_failed()));
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head>
	<title>{m.profile_heading()} · {m.app_title()}</title>
	<meta name="description" content={m.profile_intro()} />
</svelte:head>

<header class="grid border border-(--line) lg:grid-cols-[minmax(0,1.35fr)_minmax(15rem,0.65fr)]">
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
			{m.profile_kicker()}
		</p>
		<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
			{m.profile_heading()}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-(--text-muted)">
			{m.profile_intro()}
		</p>
	</div>
	<div
		class="grid content-end border-t border-(--line) bg-(--surface-muted) p-5 lg:border-l lg:border-t-0 lg:p-7"
	>
		<p class="text-xs leading-5 text-(--text-muted)">{m.profile_defaults_note()}</p>
	</div>
</header>

{#if loading || redirecting}
	<p class="mt-8 border border-(--line) bg-(--surface-muted) p-6 text-sm" role="status">
		{redirecting ? m.auth_redirecting_to_sign_in() : m.profile_loading()}
	</p>
{:else if authState.currentUser}
	<Card.Root class="mt-8 grid gap-0 py-0 lg:grid-cols-[minmax(13rem,0.38fr)_minmax(0,1fr)]">
		<Card.Header class="bg-muted p-5 sm:p-6 lg:border-r">
			<Card.Title role="heading" aria-level={2}>{m.profile_identity_heading()}</Card.Title>
			<dl class="mt-5 border-y border-(--line) py-4">
				<dt class="text-xs font-semibold uppercase tracking-[0.12em] text-(--text-muted)">
					{m.field_email()}
				</dt>
				<dd class="font-mono-data mt-2 break-all text-sm">{authState.currentUser.email}</dd>
			</dl>
			<Card.Description class="mt-4 text-xs leading-5">{m.profile_email_note()}</Card.Description>
		</Card.Header>

		<form aria-busy={saving} onsubmit={handleSubmit}>
			<Card.Content class="grid gap-5 p-5 sm:p-6">
				<ErrorSummary errors={formErrors} />
				<FormField.Group class="gap-5 md:grid md:grid-cols-2">
					<Field
						label={m.field_first_name()}
						name="first_name"
						autocomplete="given-name"
						required
						maxlength={150}
						error={fieldErrors.first_name?.[0]}
						bind:value={firstName}
					/>
					<Field
						label={m.field_last_name()}
						name="last_name"
						autocomplete="family-name"
						required
						maxlength={150}
						error={fieldErrors.last_name?.[0]}
						bind:value={lastName}
					/>
				</FormField.Group>
				<InstitutionCombobox
					initialLabel={authState.currentUser.institution?.label ?? ''}
					error={
						fieldErrors.institution?.[0] ??
						fieldErrors.institution_id?.[0] ??
						fieldErrors.institution_label?.[0]
					}
					bind:choice={institutionChoice}
				/>
			</Card.Content>
			<Card.Footer class="flex flex-wrap justify-between gap-4 border-t">
				<p class="text-sm text-success" role={saved ? 'status' : undefined}>
					{saved ? m.profile_saved() : ''}
				</p>
				<Button class="min-h-11" type="submit" disabled={saving}>
					{#if saving}<Spinner aria-hidden="true" />{/if}
					{saving ? m.profile_saving() : m.action_save_profile()}
				</Button>
			</Card.Footer>
		</form>
	</Card.Root>
{:else}
	<section class="mt-8">
		<ErrorSummary errors={formErrors} />
	</section>
{/if}
