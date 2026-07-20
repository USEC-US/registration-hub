<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

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

<div class="grid gap-2">
	<label class="text-sm font-semibold text-(--text)" for={name}>{label}</label>
	<input
		class="min-h-11 border border-(--line) bg-white px-3 py-2 text-(--text) shadow-none focus:border-(--accent) focus:ring-0"
		id={name}
		{name}
		{type}
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
		<p class="text-xs leading-5 text-(--text-muted)" id={hintId}>{hint}</p>
	{/if}
	{#if error}
		<p class="text-sm text-(--error)" id={errorId}>{error}</p>
	{/if}
</div>
