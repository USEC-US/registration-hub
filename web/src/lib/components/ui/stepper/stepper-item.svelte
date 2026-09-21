<script lang="ts">
	import { cn } from '$lib/utils';
	import { untrack } from 'svelte';
	import { useStepperItem } from '$lib/components/ui/stepper/stepper.svelte.js';
	import type { StepperItemProps } from '$lib/components/ui/stepper/types';

	const uid = $props.id();

	let { id = uid, class: className, children, ...rest }: StepperItemProps = $props();

	const stepperItemState = useStepperItem({ id: untrack(() => id) });
</script>

<div
	data-slot="stepper-item"
	class={cn(
		'group/stepper-item relative flex',
		{
			'flex-1': !stepperItemState.isLast
		},
		className
	)}
	{...stepperItemState.props}
	{...rest}
>
	{@render children?.()}
</div>
