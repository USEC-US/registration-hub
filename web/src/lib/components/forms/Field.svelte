<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

	interface Props {
		label: string;
		name: string;
		value?: string;
		error?: string;
		type?: HTMLInputAttributes['type'];
		autocomplete?: HTMLInputAttributes['autocomplete'];
		spellcheck?: HTMLInputAttributes['spellcheck'];
	}

	let {
		label,
		name,
		value = $bindable(''),
		error,
		type = 'text',
		autocomplete,
		spellcheck
	}: Props = $props();
	const errorId = $derived(`${name}-error`);
</script>

<div class="grid gap-2">
	<label class="text-sm font-semibold text-[var(--text)]" for={name}>{label}</label>
	<input
		class="min-h-11 border border-[var(--line)] bg-white px-3 py-2 text-[var(--text)] shadow-none focus:border-[var(--accent)] focus:ring-0"
		id={name}
		{name}
		{type}
		{autocomplete}
		{spellcheck}
		bind:value
		aria-describedby={error ? errorId : undefined}
		aria-invalid={error ? 'true' : undefined}
	/>
	{#if error}
		<p class="text-sm text-[var(--error)]" id={errorId}>{error}</p>
	{/if}
</div>
