<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { searchInstitutions } from '$lib/api/institutions';
	import type { Institution, InstitutionChoice } from '$lib/api/types';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';
	import * as m from '$lib/paraglide/messages';

	interface Props {
		choice?: InstitutionChoice;
		error?: string;
		initialLabel?: string;
	}

	let { choice = $bindable(), error, initialLabel = '' }: Props = $props();
	let inputValue = $state('');
	let results = $state<Institution[]>([]);
	let loading = $state(false);
	let activeIndex = $state(-1);
	let requestId = 0;
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;
	const inputId = $props.id();
	const listboxId = `${inputId}-results`;
	const errorId = `${inputId}-error`;

	onMount(() => {
		inputValue = initialLabel;
	});

	function chooseInstitution(institution: Institution): void {
		choice = { institution_id: institution.id };
		inputValue = institution.label;
		results = [];
		activeIndex = -1;
	}

	function chooseCustomLabel(): void {
		const label = inputValue.trim();
		if (!label) return;
		choice = { institution_label: label };
		results = [];
		activeIndex = -1;
	}

	async function search(query: string): Promise<void> {
		const currentRequest = ++requestId;
		if (!query) {
			results = [];
			loading = false;
			return;
		}

		loading = true;
		try {
			const nextResults = await searchInstitutions(query);
			if (currentRequest !== requestId) return;
			results = nextResults;
			activeIndex = -1;
		} catch {
			if (currentRequest !== requestId) return;
			results = [];
		} finally {
			if (currentRequest === requestId) loading = false;
		}
	}

	function handleInput(): void {
		choice = undefined;
		const query = inputValue.trim();
		if (debounceTimer) clearTimeout(debounceTimer);
		requestId += 1;
		results = [];
		activeIndex = -1;
		loading = Boolean(query);
		debounceTimer = setTimeout(() => void search(query), 200);
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (event.key === 'ArrowDown' && results.length > 0) {
			event.preventDefault();
			activeIndex = Math.min(activeIndex + 1, results.length - 1);
		} else if (event.key === 'ArrowUp' && results.length > 0) {
			event.preventDefault();
			activeIndex = Math.max(activeIndex - 1, 0);
		} else if (event.key === 'Enter' && activeIndex >= 0) {
			event.preventDefault();
			chooseInstitution(results[activeIndex]);
		} else if (event.key === 'Escape') {
			results = [];
			activeIndex = -1;
		}
	}

	onDestroy(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
	});
</script>

<Field.Field data-invalid={error ? true : undefined}>
	<Field.Label for={inputId}>{m.field_institution()}</Field.Label>
	<Input
		id={inputId}
		name="institution"
		autocomplete="organization"
		placeholder={m.institution_search_placeholder()}
		bind:value={inputValue}
		oninput={handleInput}
		onkeydown={handleKeydown}
		role="combobox"
		aria-autocomplete="list"
		aria-controls={listboxId}
		aria-expanded={results.length > 0}
		aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
		aria-describedby={error ? errorId : undefined}
		aria-invalid={error ? 'true' : undefined}
	/>
	{#if results.length > 0}
		<ul id={listboxId} role="listbox" class="mt-2 divide-y border border-(--line) bg-card">
			{#each results as institution, index (institution.id)}
				<li>
					<button
						id={`${listboxId}-${index}`}
						type="button"
						role="option"
						aria-selected={activeIndex === index}
						class="grid w-full gap-1 px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
						onclick={() => chooseInstitution(institution)}
					>
						<span class="font-semibold">{institution.label}</span>
						{#if institution.shortName || institution.code || institution.location}
							<span class="text-xs text-muted-foreground">
								{[institution.shortName, institution.code, institution.location]
									.filter(Boolean)
									.join(' · ')}
							</span>
						{/if}
					</button>
				</li>
			{/each}
		</ul>
	{:else if inputValue.trim() && !loading}
		<div class="mt-2 flex flex-wrap items-center justify-between gap-3 border border-(--line) bg-muted p-3">
			<p class="text-sm text-muted-foreground">{m.institution_no_matches()}</p>
			<button
				type="button"
				class="text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-offset-2 focus-visible:outline-ring"
				onclick={chooseCustomLabel}
			>
				{m.institution_use_custom({ label: inputValue.trim() })}
			</button>
		</div>
	{/if}
	{#if error}
		<Field.Error id={errorId}>{error}</Field.Error>
	{/if}
</Field.Field>
