<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { ApiRequestError } from '$lib/api/client';
	import { getCurrentUser, updateCurrentUser } from '$lib/api/auth';
	import type { CurrentUser } from '$lib/api/types';
	import { replaceInternalLocation } from '$lib/auth/navigation';
	import { clearSession, getAccessToken } from '$lib/auth/session';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import Field from '$lib/components/forms/Field.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import { localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { onMount } from 'svelte';

	let accessToken = $state<string | null>(null);
	let currentUser = $state<CurrentUser | null>(null);
	let firstName = $state('');
	let lastName = $state('');
	let school = $state('');
	let loading = $state(true);
	let saving = $state(false);
	let saved = $state(false);
	let redirecting = $state(false);
	let fieldErrors = $state<Record<string, string[]>>({});
	let formErrors = $state<string[]>([]);

	function signInHref(): string {
		const currentHref = `${page.url.pathname}${page.url.search}${page.url.hash}`;
		return `${resolve(localizeInternalHref('/auth/sign-in'))}?redirectTo=${encodeURIComponent(currentHref)}`;
	}

	async function redirectToSignIn(clearTokens: boolean): Promise<void> {
		if (redirecting) return;
		redirecting = true;
		if (clearTokens) clearSession();
		replaceInternalLocation(signInHref());
	}

	function isAuthenticationError(cause: unknown): boolean {
		return cause instanceof ApiRequestError && (cause.status === 401 || cause.status === 403);
	}

	onMount(async () => {
		accessToken = getAccessToken();
		if (!accessToken) {
			loading = false;
			await redirectToSignIn(false);
			return;
		}

		try {
			currentUser = await getCurrentUser(accessToken);
			firstName = currentUser.first_name;
			lastName = currentUser.last_name;
			school = currentUser.school;
		} catch (cause) {
			if (isAuthenticationError(cause)) {
				await redirectToSignIn(true);
				return;
			}
			({ fieldErrors, formErrors } = formErrorsFrom(cause, m.profile_load_failed()));
		} finally {
			loading = false;
		}
	});

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (saving || !accessToken) return;

		saving = true;
		saved = false;
		fieldErrors = {};
		formErrors = [];

		try {
			currentUser = await updateCurrentUser(accessToken, {
				first_name: firstName,
				last_name: lastName,
				school
			});
			firstName = currentUser.first_name;
			lastName = currentUser.last_name;
			school = currentUser.school;
			saved = true;
		} catch (cause) {
			if (isAuthenticationError(cause)) {
				await redirectToSignIn(true);
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

<header
	class="grid border border-(--line) lg:grid-cols-[minmax(0,1.35fr)_minmax(15rem,0.65fr)]"
>
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
{:else if currentUser}
	<section
		class="mt-8 grid border border-(--line) lg:grid-cols-[minmax(13rem,0.38fr)_minmax(0,1fr)]"
	>
		<div class="bg-(--surface-muted) p-5 sm:p-6 lg:border-r lg:border-(--line)">
			<h2 class="font-heading text-xl font-semibold">{m.profile_identity_heading()}</h2>
			<dl class="mt-5 border-y border-(--line) py-4">
				<dt class="text-xs font-semibold uppercase tracking-[0.12em] text-(--text-muted)">
					{m.field_email()}
				</dt>
				<dd class="font-mono-data mt-2 break-all text-sm">{currentUser.email}</dd>
			</dl>
			<p class="mt-4 text-xs leading-5 text-(--text-muted)">{m.profile_email_note()}</p>
		</div>

		<form class="grid gap-5 p-5 sm:p-6" aria-busy={saving} onsubmit={handleSubmit}>
			<ErrorSummary errors={formErrors} />
			<div class="grid gap-5 md:grid-cols-2">
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
			</div>
			<Field
				label={m.field_school()}
				name="school"
				autocomplete="organization"
				maxlength={128}
				error={fieldErrors.school?.[0]}
				bind:value={school}
			/>
			<div
				class="flex flex-wrap items-center justify-between gap-4 border-t border-(--line) pt-5"
			>
				<p class="text-sm text-(--success)" role={saved ? 'status' : undefined}>
					{saved ? m.profile_saved() : ''}
				</p>
				<button
					class="min-h-11 border border-accent bg-accent px-5 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60"
					type="submit"
					disabled={saving}
				>
					{saving ? m.profile_saving() : m.action_save_profile()}
				</button>
			</div>
		</form>
	</section>
{:else}
	<section class="mt-8">
		<ErrorSummary errors={formErrors} />
	</section>
{/if}
