<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { signIn } from '$lib/api/auth';
	import { saveSession } from '$lib/auth/session';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import Field from '$lib/components/forms/Field.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref, sanitizeInternalRedirect } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';

	let email = $state('');
	let password = $state('');
	let submitting = $state(false);
	let fieldErrors = $state<Record<string, string[]>>({});
	let formErrors = $state<string[]>([]);

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting) return;

		submitting = true;
		fieldErrors = {};
		formErrors = [];

		try {
			const tokens = await signIn(email, password);
			saveSession(tokens);
			await goto(resolve(sanitizeInternalRedirect(page.url.searchParams.get('redirectTo'))));
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

<header
	class="grid border border-(--line) lg:grid-cols-[minmax(0,1.25fr)_minmax(16rem,0.75fr)]"
>
	<div class="p-5 sm:p-7 lg:p-9">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-(--accent)">
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

<section
	class="mt-8 grid border border-(--line) lg:grid-cols-[minmax(13rem,0.42fr)_minmax(0,1fr)]"
>
	<header class="bg-(--surface-muted) p-5 sm:p-6 lg:border-r lg:border-(--line)">
		<h2 class="font-heading text-xl font-semibold">{m.auth_credentials_heading()}</h2>
		<p class="mt-3 text-sm leading-6 text-(--text-muted)">{m.auth_credentials_intro()}</p>
	</header>

	<form class="grid gap-5 p-5 sm:p-6" aria-busy={submitting} onsubmit={handleSubmit}>
		<ErrorSummary errors={formErrors} />
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
		<div
			class="flex flex-wrap items-center justify-between gap-4 border-t border-(--line) pt-5"
		>
			<p class="text-sm text-(--text-muted)">
				{m.auth_need_account()}
				<a
					class="font-semibold text-(--accent)"
					href={resolve(localizeInternalHref('/auth/register'))}>{m.action_create_account()}</a
				>
			</p>
			<button
				class="min-h-11 border border-(--accent) bg-(--accent) px-5 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60"
				type="submit"
				disabled={submitting}
			>
				{submitting ? m.auth_signing_in() : m.nav_sign_in()}
			</button>
		</div>
	</form>
</section>
