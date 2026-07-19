<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { localizeCurrentHref, localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale, locales } from '$lib/paraglide/runtime';
	import type { Snippet } from 'svelte';

	interface Props {
		children: Snippet;
	}

	type Locale = (typeof locales)[number];

	let { children }: Props = $props();

	function localeName(locale: Locale): string {
		return locale === 'vi' ? m.locale_name_vi() : m.locale_name_en();
	}
</script>

<a
	class="fixed left-4 top-4 z-50 -translate-y-24 border border-[var(--accent)] bg-white px-3 py-2 text-sm font-semibold text-[var(--accent)] focus:translate-y-0"
	href="#main-content"
>
	{m.skip_to_content()}
</a>

<div class="min-h-screen bg-[var(--board)] text-[var(--text)]">
	<header class="border-b border-[var(--line)] bg-white">
		<nav
			class="mx-auto grid max-w-6xl grid-cols-1 border-x border-[var(--line)] lg:grid-cols-[minmax(18rem,1fr)_auto_auto]"
			aria-label={m.nav_primary_label()}
		>
			<a
				class="flex items-center gap-3 px-4 py-4 sm:px-6"
				href={resolve(localizeInternalHref('/'))}
			>
				<span class="bracket-node" aria-hidden="true"></span>
				<span class="min-w-0">
					<span class="font-heading block text-lg font-semibold leading-tight sm:text-xl">
						{m.app_title()}
					</span>
					<span
						class="mt-1 block text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]"
					>
						{m.app_kicker()}
					</span>
				</span>
			</a>

			<div class="flex flex-wrap justify-center items-center border-t border-[var(--line)] lg:border-l lg:border-t-0">
				<a
					class="px-4 py-4 text-sm font-medium"
					href={resolve(localizeInternalHref('/tournaments'))}>{m.nav_tournaments()}</a
				>
				<a
					class="px-4 py-4 text-sm font-medium"
					href={resolve(localizeInternalHref('/account/registrations'))}
				>
					{m.nav_my_registrations()}
				</a>
				<a
					class="px-4 py-4 text-sm font-medium"
					href={resolve(localizeInternalHref('/account/profile'))}>{m.nav_profile()}</a
				>
				<a
					class="px-4 py-4 text-sm font-medium"
					href={resolve(localizeInternalHref('/auth/sign-in'))}>{m.nav_sign_in()}</a
				>
			</div>

			<div
				class="flex items-stretch border-t border-[var(--line)] lg:border-l lg:border-t-0"
				aria-label={m.locale_switcher_label()}
			>
				<span
					class="flex items-center border-r border-[var(--line)] px-3 text-xs font-semibold text-[var(--text-muted)]"
				>
					{m.locale_switcher_label()}
				</span>
				{#each locales as locale (locale)}
					<a
						class="flex min-w-11 items-center justify-center px-3 py-4 text-xs font-semibold uppercase aria-[current=page]:text-[var(--accent)] aria-[current=page]:shadow-[inset_0_-2px_var(--accent)]"
						href={resolve(localizeCurrentHref(page.url, locale))}
						data-sveltekit-reload
						hreflang={locale}
						lang={locale}
						aria-label={localeName(locale)}
						aria-current={getLocale() === locale ? 'page' : undefined}
					>
						{locale}
					</a>
				{/each}
			</div>
		</nav>
	</header>

	<main
		class="mx-auto min-h-[calc(100vh-5rem)] max-w-6xl border-x border-[var(--line)] bg-white px-4 py-8 sm:px-6 sm:py-10"
		id="main-content"
	>
		{@render children()}
	</main>
</div>
