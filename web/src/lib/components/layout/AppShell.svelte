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
			class="mx-auto grid max-w-7xl grid-cols-1 border-x border-(--line) lg:grid-cols-[minmax(18rem,1fr)_auto_auto] bg-white border-b"
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

			<div
				class="flex flex-wrap justify-center items-center border-t border-(--line) lg:border-l lg:border-t-0"
			>
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
				class="flex items-stretch border-t border-(--line) lg:border-l lg:border-t-0"
				aria-label={m.locale_switcher_label()}
			>
				<span
					class="flex items-center border-r border-(--line) px-3 text-xs font-semibold text-(--text-muted)"
				>
					{m.locale_switcher_label()}
				</span>
				{#each locales as locale (locale)}
					<a
						class="flex min-w-11 items-center justify-center px-3 py-4 text-xs font-semibold uppercase aria-[current=page]:text-accent aria-[current=page]:shadow-[inset_0_-2px_var(--accent)]"
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
