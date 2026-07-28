<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { registerAccount, signIn } from '$lib/api/auth';
	import { saveSession } from '$lib/auth/session';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import Field from '$lib/components/forms/Field.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Card from '$lib/components/ui/card';
	import * as FormField from '$lib/components/ui/field';
	import { Spinner } from '$lib/components/ui/spinner';

	type RegistrationPhase = 'form' | 'signing-in' | 'recovery';

	let email = $state('');
	let password = $state('');
	let firstName = $state('');
	let lastName = $state('');
	let school = $state('');
	let phase = $state<RegistrationPhase>('form');
	let submitting = $state(false);
	let recoveryEmail = $state('');
	let fieldErrors = $state<Record<string, string[]>>({});
	let formErrors = $state<string[]>([]);

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting || phase !== 'form') return;

		submitting = true;
		fieldErrors = {};
		formErrors = [];

		try {
			const account = await registerAccount({
				email,
				password,
				first_name: firstName,
				last_name: lastName,
				school
			});
			recoveryEmail = account.email;
			phase = 'signing-in';

			try {
				const tokens = await signIn(account.email, password);
				saveSession(tokens);
				await goto(resolve(localizeInternalHref('/account/profile')));
			} catch {
				password = '';
				phase = 'recovery';
			}
		} catch (cause) {
			({ fieldErrors, formErrors } = formErrorsFrom(cause, m.auth_register_failed()));
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>{m.auth_register_heading()} · {m.app_title()}</title>
	<meta name="description" content={m.auth_register_intro()} />
</svelte:head>

<header class="grid border border-(--line) lg:grid-cols-[minmax(0,1.25fr)_minmax(16rem,0.75fr)]">
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
			{m.auth_register_kicker()}
		</p>
		<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
			{m.auth_register_heading()}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-(--text-muted)">
			{m.auth_register_intro()}
		</p>
	</div>
	<div
		class="grid content-end border-t border-(--line) bg-(--surface-muted) p-5 lg:border-l lg:border-t-0 lg:p-7"
	>
		<p class="text-xs leading-5 text-(--text-muted)">{m.auth_profile_defaults_note()}</p>
	</div>
</header>

{#if phase === 'recovery'}
	<section
		class="mt-8 grid border border-(--line) lg:grid-cols-[minmax(13rem,0.42fr)_minmax(0,1fr)]"
	>
		<div class="bg-(--surface-muted) p-5 sm:p-6 lg:border-r lg:border-(--line)">
			<span class="bracket-node" aria-hidden="true"></span>
			<p class="font-mono-data mt-4 text-xs text-(--text-muted)">{recoveryEmail}</p>
		</div>
		<div class="p-5 sm:p-7" role="status">
			<h2 class="font-heading text-2xl font-semibold">{m.auth_account_created_heading()}</h2>
			<p class="mt-3 max-w-2xl text-sm leading-6 text-(--text-muted)">
				{m.auth_account_created_recovery()}
			</p>
			<a
				class="mt-6 inline-flex min-h-11 items-center border border-accent px-4 py-2 text-sm font-semibold text-accent"
				href={resolve(localizeInternalHref('/auth/sign-in'))}>{m.action_go_to_sign_in()}</a
			>
		</div>
	</section>
{:else if phase === 'signing-in'}
	<p class="mt-8 border border-(--line) bg-(--surface-muted) p-6 text-sm" role="status">
		{m.auth_account_created_signing_in()}
	</p>
{:else}
	<Card.Root class="mt-8 grid gap-0 py-0 lg:grid-cols-[minmax(13rem,0.34fr)_minmax(0,1fr)]">
		<Card.Header class="bg-muted p-5 sm:p-6 lg:border-r">
			<Card.Title role="heading" aria-level={2}>{m.auth_identity_heading()}</Card.Title>
			<Card.Description class="mt-3 leading-6">{m.auth_identity_intro()}</Card.Description>
		</Card.Header>

		<form aria-busy={submitting} onsubmit={handleSubmit}>
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
					<Field
						label={m.field_email()}
						name="email"
						type="email"
						autocomplete="username"
						spellcheck={false}
						required
						maxlength={254}
						error={fieldErrors.email?.[0]}
						bind:value={email}
					/>
					<Field
						label={m.field_password()}
						name="password"
						type="password"
						autocomplete="new-password"
						required
						minlength={8}
						maxlength={128}
						hint={m.auth_password_hint()}
						error={fieldErrors.password?.[0]}
						bind:value={password}
					/>
					<Field
						label={m.field_school()}
						name="school"
						autocomplete="organization"
						maxlength={128}
						error={fieldErrors.school?.[0]}
						bind:value={school}
					/>
				</FormField.Group>
			</Card.Content>
			<Card.Footer class="flex flex-wrap justify-between gap-4 border-t">
				<p class="text-sm text-muted-foreground">
					{m.auth_have_account()}
					<a
						class="font-semibold text-primary"
						href={resolve(localizeInternalHref('/auth/sign-in'))}>{m.nav_sign_in()}</a
					>
				</p>
				<Button class="min-h-11" type="submit" disabled={submitting}>
					{#if submitting}<Spinner aria-hidden="true" />{/if}
					{submitting ? m.auth_creating_account() : m.action_create_account()}
				</Button>
			</Card.Footer>
		</form>
	</Card.Root>
{/if}
