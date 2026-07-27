<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';

	interface Props {
		label: string;
		name: string;
		value?: string;
		error?: string;
		hint?: string;
		type?: HTMLInputAttributes['type'];
		autocomplete?: HTMLInputAttributes['autocomplete'];
		spellcheck?: HTMLInputAttributes['spellcheck'];
		required?: HTMLInputAttributes['required'];
		minlength?: HTMLInputAttributes['minlength'];
		maxlength?: HTMLInputAttributes['maxlength'];
	}

	let {
		label,
		name,
		value = $bindable(''),
		error,
		hint,
		type = 'text',
		autocomplete,
		spellcheck,
		required,
		minlength,
		maxlength
	}: Props = $props();
	const errorId = $derived(`${name}-error`);
	const hintId = $derived(`${name}-hint`);
	const describedBy = $derived(
		[hint ? hintId : undefined, error ? errorId : undefined].filter(Boolean).join(' ') || undefined
	);
</script>

<Field.Field data-invalid={error ? true : undefined}>
	<Field.Label for={name}>{label}</Field.Label>
	<Input
		id={name}
		{name}
		type={type ?? undefined}
		{autocomplete}
		{spellcheck}
		{required}
		{minlength}
		{maxlength}
		bind:value
		aria-describedby={describedBy}
		aria-invalid={error ? 'true' : undefined}
	/>
	{#if hint}
		<Field.Description id={hintId}>{hint}</Field.Description>
	{/if}
	{#if error}
		<Field.Error id={errorId}>{error}</Field.Error>
	{/if}
</Field.Field>
