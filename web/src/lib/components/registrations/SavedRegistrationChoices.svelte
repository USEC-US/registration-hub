<script lang="ts">
	import type { SavedRegistrationAccess } from '$lib/registrations/browser-storage';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import * as m from '$lib/paraglide/messages';
	import { localizeInternalHref } from '$lib/navigation';
	import { resolve } from '$app/paths';
	let {
		entries,
		onrecover,
		onforget
	}: {
		entries: SavedRegistrationAccess[];
		onrecover: (entry: SavedRegistrationAccess) => void;
		onforget: (entry: SavedRegistrationAccess) => void;
	} = $props();
</script>

{#if entries.length}<Card.Root class="mb-6"
		><Card.Header
			><Card.Title>{m.stages_saved_entries()}</Card.Title><Card.Description
				>{m.stages_saved_progress()}</Card.Description
			></Card.Header
		><Card.Content class="flex flex-col gap-3"
			>{#each entries as entry (entry.credential)}<div class="flex flex-wrap items-center gap-3">
					{#if entry.attemptState === 'submitted'}<Button
							variant="outline"
							href={resolve(localizeInternalHref(`/registrations/${entry.registrationId}/payment`))}
							>{m.stages_view_saved({ id: entry.registrationId })}</Button
						><Button variant="destructive" onclick={() => onforget(entry)}
							>{m.stages_forget()}</Button
						>{:else}<Button onclick={() => onrecover(entry)}>{m.stages_recover()}</Button>{/if}
				</div>{/each}</Card.Content
		></Card.Root
	>{/if}
