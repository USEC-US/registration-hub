<script lang="ts">
	import { dev } from '$app/environment';
	import { page } from '$app/state';
	import RichText from '$lib/i18n/RichText.svelte';
	import * as m from '$lib/paraglide/messages';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { isStagingHost } from '$lib/staging';

	const FACEBOOK_URL = 'https://facebook.com/hcmusec';
	const REPO_URL = 'https://github.com/USEC-US/registration-hub';

	const isStaging = $derived(isStagingHost(page.url, dev));
</script>

{#if isStaging}
	<Dialog.Root>
		<div
			class="sticky top-0 z-40 w-full border-b border-amber-600/40 bg-amber-400 text-amber-950 shadow-xs"
		>
			<Dialog.Trigger
				class="group flex w-full cursor-pointer items-center justify-center gap-2 px-4 py-2 text-center font-bold tracking-wider uppercase transition-colors hover:bg-amber-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-950 focus-visible:ring-offset-2 sm:text-sm"
			>
				<span class="font-bold text-xl">{m.staging_banner_text()}</span>
			</Dialog.Trigger>
		</div>

		<Dialog.Content class="sm:max-w-md">
			<Dialog.Header>
				<Dialog.Title class="flex items-center gap-2 text-base font-bold sm:text-lg">
					<span aria-hidden="true">🚧</span>
					<span>{m.staging_dialog_title()}</span>
				</Dialog.Title>
			</Dialog.Header>

			<div class="space-y-3 text-sm leading-relaxed text-foreground">
				<p>
					{m.staging_dialog_p1()}
				</p>
				<p>
					<RichText message={m.staging_dialog_p2} inputs={{}}>
						{#snippet linkOverride(p)}
							<a
								href={FACEBOOK_URL}
								target="_blank"
								rel="noopener noreferrer"
								class="font-semibold text-primary underline underline-offset-2 hover:text-primary/80"
							>
								{@render p.children?.()}
							</a>
						{/snippet}
					</RichText>
				</p>
				<p>
					<RichText message={m.staging_dialog_p3} inputs={{}}>
						{#snippet linkOverride(p)}
							<a
								href={REPO_URL}
								target="_blank"
								rel="noopener noreferrer"
								class="font-semibold text-primary underline underline-offset-2 hover:text-primary/80"
							>
								{@render p.children?.()}
							</a>
						{/snippet}
					</RichText>
				</p>
			</div>

			<Dialog.Footer class="sm:justify-end">
				<Dialog.Close>
					{#snippet child({ props })}
						<Button variant="outline" {...props}>
							{m.staging_dialog_close()}
						</Button>
					{/snippet}
				</Dialog.Close>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Root>
{/if}
