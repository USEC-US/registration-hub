<script lang="ts">
	import * as Stepper from '$lib/components/ui/stepper';
	import Check from '@lucide/svelte/icons/check';
	import type { DraftStage } from '$lib/registrations/browser-storage';
	import * as m from '$lib/paraglide/messages';
	let {
		stage,
		completed,
		disabled = false,
		onnavigate
	}: {
		stage: DraftStage;
		completed: DraftStage[];
		disabled?: boolean;
		onnavigate: (stage: DraftStage) => void;
	} = $props();
	const stages: DraftStage[] = ['details', 'roster', 'review'];
	const current = $derived(stages.indexOf(stage) + 1);
</script>

<nav
	aria-label={m.stages_navigation()}
	class="registration-steps rounded-xl border bg-muted/20 px-2 py-5 sm:px-6 sm:py-6"
>
	<Stepper.Root
		bind:step={
			() => current,
			(next) => {
				const target = stages[next - 1];
				if (!disabled && target && target !== stage && completed.includes(target))
					onnavigate(target);
			}
		}
	>
		<Stepper.Nav class="grid grid-cols-3">
			{#each stages as item, index (item)}
				<Stepper.Item class="min-w-0 justify-center">
					<Stepper.Trigger
						type="button"
						class="w-full items-center gap-2 rounded-lg px-1 disabled:cursor-not-allowed"
						aria-current={stage === item ? 'step' : undefined}
						aria-label={`${index + 1}. ${item === 'details' ? m.registration_details_heading() : item === 'roster' ? m.roster_heading() : m.stages_review()}`}
						disabled={disabled || (item !== stage && !completed.includes(item))}
					>
						<Stepper.Indicator class="size-9 ring-4" aria-hidden="true">
							{#if index + 1 < current}<Check />{:else}{index + 1}{/if}
						</Stepper.Indicator>
						<Stepper.Title
							>{item === 'details'
								? m.registration_details_heading()
								: item === 'roster'
									? m.roster_heading()
									: m.stages_review()}</Stepper.Title
						>
						<Stepper.Description class="hidden sm:block"
							>{item === 'details'
								? m.registration_step_details_hint()
								: item === 'roster'
									? m.registration_step_roster_hint()
									: m.registration_step_review_hint()}</Stepper.Description
						>
					</Stepper.Trigger>
					<Stepper.Separator aria-hidden="true" />
				</Stepper.Item>
			{/each}
		</Stepper.Nav>
	</Stepper.Root>
</nav>

<style>
	.registration-steps :global([data-slot='stepper-title']) {
		font-size: 0.875rem;
		line-height: 1.4;
	}
	.registration-steps :global([data-slot='stepper-separator']) {
		top: 17px;
		left: 50%;
		height: 2px;
	}
	.registration-steps
		:global([data-slot='stepper-trigger'][data-state='active'] [data-slot='stepper-title']) {
		color: var(--primary);
		font-weight: 600;
	}
	@media (max-width: 400px) {
		.registration-steps :global([data-slot='stepper-title']) {
			font-size: 0.75rem;
		}
	}
</style>
