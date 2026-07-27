<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { getCurrentUser } from '$lib/api/auth';
	import { ApiRequestError } from '$lib/api/client';
	import type { CurrentUser } from '$lib/api/types';
	import { clearSession, getAccessToken } from '$lib/auth/session';
	import { localizeCurrentHref, localizeInternalHref } from '$lib/navigation';
	import * as m from '$lib/paraglide/messages';
	import { getLocale, locales } from '$lib/paraglide/runtime';
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';
	import { ChevronDown } from '@lucide/svelte';
	import Discord from '$lib/components/icons/Discord.svelte';
	import Facebook from '$lib/components/icons/Facebook.svelte';
	import Gmail from '$lib/components/icons/Gmail.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';

	interface Props {
		children: Snippet;
	}

	type Locale = (typeof locales)[number];
	type AccountNavigationState = 'loading' | 'signed-out' | 'signed-in' | 'unavailable';

	let { children }: Props = $props();
	let accountNavigationState = $state<AccountNavigationState>('loading');
	let currentUser = $state<CurrentUser | null>(null);

	function localeName(locale: Locale): string {
		return locale === 'vi' ? m.locale_name_vi() : m.locale_name_en();
	}

	function changeLocale(locale: Locale): void {
		if (locale === getLocale()) return;

		window.location.assign(resolve(localizeCurrentHref(page.url, locale)));
	}

	function isAuthenticationError(cause: unknown): boolean {
		return cause instanceof ApiRequestError && (cause.status === 401 || cause.status === 403);
	}

	function welcomeName(user: CurrentUser): string {
		return getLocale() === 'vi'
			? `${user.last_name} ${user.first_name}`
			: `${user.first_name} ${user.last_name}`;
	}

	onMount(async () => {
		const accessToken = getAccessToken();
		if (!accessToken) {
			accountNavigationState = 'signed-out';
			return;
		}

		try {
			currentUser = await getCurrentUser(accessToken);
			accountNavigationState = 'signed-in';
		} catch (cause) {
			if (isAuthenticationError(cause)) {
				clearSession();
				accountNavigationState = 'signed-out';
				return;
			}

			accountNavigationState = 'unavailable';
		}
	});

	const socials = {
		facebook: {
			href: 'https://facebook.com/hcmusec',
			icon: Facebook
		},
		discord: {
			href: 'https://discord.gg/Ztkk8csTck',
			icon: Discord
		},
		email: {
			href: 'mailto:hcmusec@gmail.com',
			icon: Gmail
		}
	};
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
			class="mx-auto max-w-7xl border-x border-b border-(--line) bg-white flex"
			aria-label={m.nav_primary_label()}
		>
			<a
				class="flex flex-1 items-center gap-3 px-4 py-4 sm:px-6"
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

			<div class="flex min-h-11 border-(--line)">
				<a
					class="flex min-w-(--nav-cell-min) flex-1 items-center justify-center px-4 py-2 text-center text-lg font-medium"
					style:--nav-cell-min="9rem"
					href={resolve(localizeInternalHref('/tournaments'))}>{m.nav_tournaments()}</a
				>
				<span
					class="flex min-w-(--nav-cell-min) flex-1 cursor-not-allowed items-center justify-center px-4 py-2 text-center text-lg font-medium text-(--text-muted)"
					style:--nav-cell-min="7rem"
					aria-disabled="true"
					title={m.nav_rules_unavailable()}
				>
					{m.nav_rules()}
				</span>
			</div>
		</nav>

		<nav
			class="mx-auto max-w-7xl border-x border-b border-(--line) bg-white"
			aria-label={m.nav_secondary_label()}
		>
			<div class="flex min-h-11 justify-end">
				<div class="flex">
					{#if accountNavigationState === 'signed-in' && currentUser}
						<a
							class="flex items-center border-(--line) px-4 py-2 text-sm font-medium"
							href={resolve(localizeInternalHref('/account/profile'))}
						>
							{m.nav_welcome({ name: welcomeName(currentUser) })}
						</a>
						<a
							class="flex items-center border-(--line) px-4 py-2 text-sm font-medium"
							href={resolve(localizeInternalHref('/account/registrations'))}
						>
							{m.nav_my_registrations()}
						</a>
					{:else if accountNavigationState === 'signed-out'}
						<a
							class="flex items-center border-(--line) px-4 py-2 text-sm font-medium"
							href={resolve(localizeInternalHref('/auth/sign-in'))}>{m.nav_sign_in()}</a
						>
						<a
							class="flex items-center border-(--line) px-4 py-2 text-sm font-medium"
							href={resolve(localizeInternalHref('/auth/register'))}>{m.nav_register()}</a
						>
					{:else}
						<span class="block min-h-11 w-44" aria-hidden="true"></span>
					{/if}
				</div>
				<div class="flex items-center px-3">
					<DropdownMenu.Root>
						<DropdownMenu.Trigger>
							{#snippet child({ props })}
								<Button
									{...props}
									variant="ghost"
									size="sm"
									class="border-(--line)"
									aria-label={m.locale_switcher_label()}
								>
									{localeName(getLocale())}
									<ChevronDown />
								</Button>
							{/snippet}
						</DropdownMenu.Trigger>
						<DropdownMenu.Content align="end">
							<DropdownMenu.Group>
								<DropdownMenu.RadioGroup value={getLocale()} aria-label={m.locale_switcher_label()}>
									{#each locales as locale (locale)}
										<DropdownMenu.RadioItem
											value={locale}
											lang={locale}
											onSelect={() => changeLocale(locale)}
										>
											{localeName(locale)}
										</DropdownMenu.RadioItem>
									{/each}
								</DropdownMenu.RadioGroup>
							</DropdownMenu.Group>
						</DropdownMenu.Content>
					</DropdownMenu.Root>
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
		<div
			id="footer-container"
			class="border-t border-x flex-row mx-auto grid max-w-7xl grid-cols-1 border-(--line) lg:grid-cols-2 p-10 bg-white"
		>
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
							href={localizeInternalHref(social.href)}
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
