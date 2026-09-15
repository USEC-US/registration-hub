<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import type { DraftStage } from '$lib/registrations/browser-storage';
	import * as m from '$lib/paraglide/messages';
	let {
		stage,
		completed,
		onnavigate
	}: { stage: DraftStage; completed: DraftStage[]; onnavigate: (stage: DraftStage) => void } =
		$props();
	const stages: DraftStage[] = ['details', 'roster', 'review'];
</script>

<nav aria-label={m.stages_navigation()} class="mb-6 flex flex-wrap gap-2">
	{#each stages as item, index (item)}<Button
			type="button"
			variant={stage === item ? 'default' : 'outline'}
			aria-current={stage === item ? 'step' : undefined}
			disabled={item !== stage && !completed.includes(item)}
			onclick={() => onnavigate(item)}
			>{index + 1}. {item === 'details'
				? m.registration_details_heading()
				: item === 'roster'
					? m.roster_heading()
					: m.stages_review()}</Button
		>{/each}
</nav>
