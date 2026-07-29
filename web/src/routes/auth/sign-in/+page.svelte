<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import Field from '$lib/components/forms/Field.svelte';
	import TurnstileWidget from '$lib/components/forms/TurnstileWidget.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref, sanitizeInternalRedirect } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { authState } from '$lib/states/auth-state.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Card from '$lib/components/ui/card';
	import * as FormField from '$lib/components/ui/field';
	import { Spinner } from '$lib/components/ui/spinner';

	let email = $state('');
	let password = $state('');
	let turnstileToken = $state('');
	let submitting = $state(false);
	let fieldErrors = $state<Record<string, string[]>>({});
	let formErrors = $state<string[]>([]);

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting) return;
		if (!turnstileToken) {
			formErrors = [m.turnstile_required()];
			return;
		}

		submitting = true;
		fieldErrors = {};
		formErrors = [];

		try {
			const user = await authState.signIn(email, password, turnstileToken);
			if (!user) {
				formErrors = [m.auth_sign_in_failed()];
				return;
			}

			await goto(resolve(sanitizeInternalRedirect(page.url.searchParams.get('redirect'))));
		} catch (cause) {
			({ fieldErrors, formErrors } = formErrorsFrom(cause, m.auth_sign_in_failed()));
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>{m.auth_sign_in_heading()} · {m.app_title()}</title>
	<meta name="description" content={m.auth_sign_in_intro()} />
</svelte:head>

<header class="grid border border-(--line) lg:grid-cols-[minmax(0,1.25fr)_minmax(16rem,0.75fr)]">
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
			{m.auth_sign_in_kicker()}
		</p>
		<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
			{m.auth_sign_in_heading()}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-(--text-muted)">
			{m.auth_sign_in_intro()}
		</p>
	</div>
	<div
		class="grid content-end border-t border-(--line) bg-(--surface-muted) p-5 lg:border-l lg:border-t-0 lg:p-7"
	>
		<p class="text-xs font-semibold uppercase tracking-[0.14em] text-(--text-muted)">
			{m.auth_access_note()}
		</p>
		<span class="bracket-node mt-4" aria-hidden="true"></span>
	</div>
</header>

<Card.Root class="mt-8 grid gap-0 lg:grid-cols-[minmax(13rem,0.42fr)_minmax(0,1fr)]">
	<Card.Header class="bg-muted p-5 sm:p-6 lg:border-r">
		<Card.Title class="font-heading font-bold text-2xl" role="heading" aria-level={2}
			>{m.auth_credentials_heading()}</Card.Title
		>
		<Card.Description class="mt-3 leading-6">{m.auth_credentials_intro()}</Card.Description>
	</Card.Header>

	<form aria-busy={submitting} onsubmit={handleSubmit}>
		<Card.Content class="grid gap-5 p-5 sm:p-6">
			<ErrorSummary errors={formErrors} />
			<FormField.Group class="gap-5">
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
					autocomplete="current-password"
					required
					error={fieldErrors.password?.[0]}
					bind:value={password}
				/>
				<TurnstileWidget action="sign-in" bind:token={turnstileToken} />
			</FormField.Group>
		</Card.Content>
		<Card.Footer class="flex flex-wrap justify-between gap-4 border-t">
			<p class="text-sm text-muted-foreground">
				{m.auth_need_account()}
				<a class="font-semibold text-primary" href={resolve(localizeInternalHref('/auth/register'))}
					>{m.action_create_account()}</a
				>
			</p>
			<Button class="min-h-11" type="submit" disabled={submitting}>
				{#if submitting}<Spinner aria-hidden="true" />{/if}
				{submitting ? m.auth_signing_in() : m.nav_sign_in()}
			</Button>
		</Card.Footer>
	</form>
</Card.Root>
