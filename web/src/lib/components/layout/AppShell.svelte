<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { localizeCurrentHref, localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale, locales } from '$lib/paraglide/runtime';
	import type { Snippet } from 'svelte';
	import Discord from '$lib/components/icons/Discord.svelte'
  import Facebook from '$lib/components/icons/Facebook.svelte';
  import Gmail from '$lib/components/icons/Gmail.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	interface Props {
		children: Snippet;
	}

	type Locale = (typeof locales)[number];

	let { children }: Props = $props();

	function localeName(locale: Locale): string {
		return locale === 'vi' ? m.locale_name_vi() : m.locale_name_en();
	}

	function changeLocale(event: Event): void {
		const target = event.currentTarget;
		if (!(target instanceof HTMLSelectElement)) return;

		const locale = target.value as Locale;
		if (locale === getLocale()) return;

		window.location.assign(resolve(localizeCurrentHref(page.url, locale)));
	}

  const socials = {
    "facebook": {
      href: "https://facebook.com/hcmusec",
      icon: Facebook
    },
    "discord": {
      href: "https://discord.gg/Ztkk8csTck",
      icon: Discord
    },
    "email": {
      href: "mailto:hcmusec@gmail.com",
      icon: Gmail
    },
  }
</script>

<a
	class="fixed left-4 top-4 z-50 -translate-y-24 border border-accent bg-white px-3 py-2 text-sm font-semibold text-accent focus:translate-y-0"
	href="#main-content"
>
	{m.skip_to_content()}
</a>

<div class="min-h-screen bg-(--board) text-(--text)">
	<header class="border-(--line)">
		<nav
			class="mx-auto max-w-7xl border-x border-b border-(--line) bg-white"
			aria-label={m.nav_primary_label()}
		>
			<a
				class="flex items-center gap-3 px-4 py-4 sm:px-6"
				href={resolve(localizeInternalHref('/'))}
			>
				<picture class="shrink-0">
					<source srcset="/logo/logo.avif" type="image/avif" />
					<source srcset="/logo/logo.webp" type="image/webp" />
					<img
						class="h-12 w-12 object-contain"
						src="/logo/logo.png"
						alt=""
						width="48"
						height="48"
					/>
				</picture>
				<span class="min-w-0">
					<span class="font-heading block text-lg font-semibold leading-tight sm:text-xl">
						{m.app_title()}
					</span>
					<span
						class="mt-1 block text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-(--text-muted)"
					>
						{m.app_kicker()}
					</span>
				</span>
			</a>
		</nav>

		<nav
			class="mx-auto max-w-7xl border-x border-b border-(--line) bg-white"
			aria-label={m.nav_secondary_label()}
		>
			<div class="flex min-h-11 justify-end border-b border-(--line)">
				<a
					class="flex items-center border-l border-(--line) px-4 py-2 text-sm font-medium"
					href={resolve(localizeInternalHref('/tournaments'))}>{m.nav_tournaments()}</a
				>
				<span
					class="flex cursor-not-allowed items-center border-l border-(--line) px-4 py-2 text-sm font-medium text-(--text-muted)"
					aria-disabled="true"
					title={m.nav_rules_unavailable()}
				>
					{m.nav_rules()}
				</span>
			</div>

			<div class="flex min-h-11 justify-end">
				<div class="flex">
					<a
						class="flex items-center border-l border-(--line) px-4 py-2 text-sm font-medium"
						href={resolve(localizeInternalHref('/auth/sign-in'))}>{m.nav_sign_in()}</a
					>
					<a
						class="flex items-center border-l border-(--line) px-4 py-2 text-sm font-medium"
						href={resolve(localizeInternalHref('/auth/register'))}>{m.nav_register()}</a
					>
				</div>
				<div class="flex items-center border-l border-(--line) px-3">
					<label class="sr-only" for="locale-switcher">{m.locale_switcher_label()}</label>
					<select
						class="bg-transparent py-2 text-sm font-medium"
						id="locale-switcher"
						value={getLocale()}
						onchange={changeLocale}
					>
						{#each locales as locale (locale)}
							<option value={locale} lang={locale}>{localeName(locale)}</option>
						{/each}
					</select>
				</div>
			</div>
		</nav>
	</header>

	<main
		class="mx-auto min-h-[calc(100vh-5rem)] max-w-7xl border-x border-(--line) bg-white px-4 py-8 sm:px-6 sm:py-10"
		id="main-content"
	>
		{@render children()}
	</main>

  <footer class=" border-(--line)">
    <div id="footer-container" class="border-t border-x flex-row mx-auto grid max-w-7xl grid-cols-1 border-(--line) lg:grid-cols-2 p-10 bg-white">
      <div id="footer-app-id" class="flex flex-col">
				<picture class="shrink-0">
					<source srcset="/logo/logo.avif" type="image/avif" />
					<source srcset="/logo/logo.webp" type="image/webp" />
					<img
						class="h-16 w-16 object-contain"
						src="/logo/logo.png"
						alt=""
						width="48"
						height="48"
					/>
				</picture>
        <div class="ml-3 mt-3">
          <p class="font-heading block text-lg font-semibold leading-tight sm:text-xl">
            {m.app_title()}
          </p>
          <p
          class="mt-1 block text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-(--text-muted)"
          >
            {m.app_kicker()}
          </p>
        </div>

      </div>
      <div id="contact" class="flex flex-col">
        <div class="flex flex-wrap gap-3 flex-1">
          {#each Object.entries(socials) as [key, social] (key)}
            {@const Icon = social.icon}
            <a
              class="flex h-10 w-10 items-center justify-center rounded-full border border-(--line) text-(--text-muted) transition hover:border-accent hover:text-accent"
              href={(localizeInternalHref(social.href))}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={key}
            >
              <Icon />
            </a>
          {/each}
        </div>
        <div>
          <RichText message={m.address_title} inputs={{}} />
          <p>
            <RichText message={m.address_1} inputs={{}} />
          </p>
          <p>
            <RichText message={m.address_2} inputs={{}} />
          </p>
        </div>
      </div>
    </div>
  </footer>
</div>
