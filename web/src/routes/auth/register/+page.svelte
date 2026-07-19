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

	type RegistrationPhase = 'form' | 'signing-in' | 'recovery';

	let email = $state('');
	let password = $state('');
	let gamerTag = $state('');
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
				gamer_tag: gamerTag,
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

<header
	class="grid border border-[var(--line)] lg:grid-cols-[minmax(0,1.25fr)_minmax(16rem,0.75fr)]"
>
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
			{m.auth_register_kicker()}
		</p>
		<h1 class="font-heading mt-3 text-3xl font-semibold leading-tight sm:text-5xl">
			{m.auth_register_heading()}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-7 text-[var(--text-muted)]">
			{m.auth_register_intro()}
		</p>
	</div>
	<div
		class="grid content-end border-t border-[var(--line)] bg-[var(--surface-muted)] p-5 lg:border-l lg:border-t-0 lg:p-7"
	>
		<p class="text-xs leading-5 text-[var(--text-muted)]">{m.auth_profile_defaults_note()}</p>
	</div>
</header>

{#if phase === 'recovery'}
	<section
		class="mt-8 grid border border-[var(--line)] lg:grid-cols-[minmax(13rem,0.42fr)_minmax(0,1fr)]"
	>
		<div class="bg-[var(--surface-muted)] p-5 sm:p-6 lg:border-r lg:border-[var(--line)]">
			<span class="bracket-node" aria-hidden="true"></span>
			<p class="font-mono-data mt-4 text-xs text-[var(--text-muted)]">{recoveryEmail}</p>
		</div>
		<div class="p-5 sm:p-7" role="status">
			<h2 class="font-heading text-2xl font-semibold">{m.auth_account_created_heading()}</h2>
			<p class="mt-3 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
				{m.auth_account_created_recovery()}
			</p>
			<a
				class="mt-6 inline-flex min-h-11 items-center border border-[var(--accent)] px-4 py-2 text-sm font-semibold text-[var(--accent)]"
				href={resolve(localizeInternalHref('/auth/sign-in'))}>{m.action_go_to_sign_in()}</a
			>
		</div>
	</section>
{:else if phase === 'signing-in'}
	<p class="mt-8 border border-[var(--line)] bg-[var(--surface-muted)] p-6 text-sm" role="status">
		{m.auth_account_created_signing_in()}
	</p>
{:else}
	<section
		class="mt-8 grid border border-[var(--line)] lg:grid-cols-[minmax(13rem,0.34fr)_minmax(0,1fr)]"
	>
		<header class="bg-[var(--surface-muted)] p-5 sm:p-6 lg:border-r lg:border-[var(--line)]">
			<h2 class="font-heading text-xl font-semibold">{m.auth_identity_heading()}</h2>
			<p class="mt-3 text-sm leading-6 text-[var(--text-muted)]">{m.auth_identity_intro()}</p>
		</header>

		<form class="grid gap-5 p-5 sm:p-6" aria-busy={submitting} onsubmit={handleSubmit}>
			<ErrorSummary errors={formErrors} />
			<div class="grid gap-5 md:grid-cols-2">
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
					label={m.field_gamer_tag()}
					name="gamer_tag"
					autocomplete="nickname"
					spellcheck={false}
					maxlength={64}
					error={fieldErrors.gamer_tag?.[0]}
					bind:value={gamerTag}
				/>
				<Field
					label={m.field_school()}
					name="school"
					autocomplete="organization"
					maxlength={128}
					error={fieldErrors.school?.[0]}
					bind:value={school}
				/>
			</div>
			<div
				class="flex flex-wrap items-center justify-between gap-4 border-t border-[var(--line)] pt-5"
			>
				<p class="text-sm text-[var(--text-muted)]">
					{m.auth_have_account()}
					<a
						class="font-semibold text-[var(--accent)]"
						href={resolve(localizeInternalHref('/auth/sign-in'))}>{m.nav_sign_in()}</a
					>
				</p>
				<button
					class="min-h-11 border border-[var(--accent)] bg-[var(--accent)] px-5 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60"
					type="submit"
					disabled={submitting}
				>
					{submitting ? m.auth_creating_account() : m.action_create_account()}
				</button>
			</div>
		</form>
	</section>
{/if}
