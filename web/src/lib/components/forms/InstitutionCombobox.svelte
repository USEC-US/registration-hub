<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { searchInstitutions } from '$lib/api/institutions';
	import type { Institution, InstitutionChoice } from '$lib/api/types';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';
	import * as Popover from '$lib/components/ui/popover';
	import * as Command from '$lib/components/ui/command';
	import { Spinner } from '$lib/components/ui/spinner';
	import * as m from '$lib/paraglide/messages';

	interface Props {
		choice?: InstitutionChoice;
		error?: string;
		initialLabel?: string;
	}

	let { choice = $bindable(), error, initialLabel = '' }: Props = $props();

	let inputEl = $state<HTMLInputElement | null>(null);
	let inputValue = $state('');
	let results = $state<Institution[]>([]);
	let loading = $state(false);
	let commandValue = $state('');
	let suppressed = $state(false);
	/** Query that `results` reflects, or null while stale/not yet searched. */
	let searchedQuery = $state<string | null>(null);
	let requestId = 0;
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;

	const inputId = $props.id();
	const listboxId = `${inputId}-results`;
	const errorId = `${inputId}-error`;

	const query = $derived(inputValue.trim());
	const activeIndex = $derived(
		results.findIndex((institution) => String(institution.id) === commandValue)
	);
	const hasContent = $derived(
		loading || results.length > 0 || (query.length > 0 && searchedQuery === query)
	);
	const panelOpen = $derived(!suppressed && hasContent);

	onMount(() => {
		inputValue = initialLabel;
	});

	function focusNextField(current: HTMLElement): void {
		const root = current.closest('form') ?? document.body;
		const focusable = Array.from(
			root.querySelectorAll<HTMLElement>(
				'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
			)
		).filter((el) => el.getClientRects().length > 0);
		const index = focusable.indexOf(current);
		if (index === -1) return;
		focusable[index + 1]?.focus();
	}

	function resetSearchState(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		requestId += 1;
		results = [];
		loading = false;
		searchedQuery = null;
		commandValue = '';
	}

	function chooseInstitution(institution: Institution): void {
		choice = { institution_id: institution.id };
		inputValue = institution.label;
		resetSearchState();
		suppressed = true;
		if (inputEl) focusNextField(inputEl);
	}

	function chooseCustomLabel(): void {
		const label = inputValue.trim();
		if (!label) return;
		choice = { institution_label: label };
		resetSearchState();
		suppressed = true;
		if (inputEl) focusNextField(inputEl);
	}

	async function search(q: string): Promise<void> {
		const currentRequest = ++requestId;
		if (!q) {
			results = [];
			loading = false;
			searchedQuery = null;
			return;
		}

		loading = true;
		try {
			const nextResults = await searchInstitutions(q);
			if (currentRequest !== requestId) return;
			results = nextResults;
			searchedQuery = q;
			commandValue = '';
		} catch {
			if (currentRequest !== requestId) return;
			results = [];
			searchedQuery = q;
		} finally {
			if (currentRequest === requestId) loading = false;
		}
	}

	function handleInput(): void {
		choice = undefined;
		suppressed = false;
		const q = inputValue.trim();
		if (debounceTimer) clearTimeout(debounceTimer);
		requestId += 1;
		results = [];
		searchedQuery = null;
		commandValue = '';
		loading = Boolean(q);
		debounceTimer = setTimeout(() => void search(q), 200);
	}

	function handleFocus(): void {
		suppressed = false;
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (event.key === 'ArrowDown' && results.length > 0) {
			event.preventDefault();
			const next = Math.min(activeIndex + 1, results.length - 1);
			commandValue = String(results[next]?.id ?? '');
		} else if (event.key === 'ArrowUp' && results.length > 0) {
			event.preventDefault();
			const next = Math.max(activeIndex - 1, 0);
			commandValue = String(results[next]?.id ?? '');
		} else if (event.key === 'Enter' && activeIndex >= 0 && results[activeIndex]) {
			event.preventDefault();
			chooseInstitution(results[activeIndex]);
		} else if (event.key === 'Escape') {
			resetSearchState();
			suppressed = true;
			inputEl?.blur();
		}
	}

	function getOpen(): boolean {
		return panelOpen;
	}

	function setOpen(next: boolean): void {
		if (!next) suppressed = true;
	}

	onDestroy(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
	});
</script>

<Field.Field data-invalid={error ? true : undefined}>
	<Field.Label for={inputId}>{m.field_institution()}</Field.Label>
	<Input
		bind:ref={inputEl}
		id={inputId}
		name="institution"
		autocomplete="organization"
		placeholder={m.institution_search_placeholder()}
		bind:value={inputValue}
		oninput={handleInput}
		onkeydown={handleKeydown}
		onfocus={handleFocus}
		role="combobox"
		aria-autocomplete="list"
		aria-controls={listboxId}
		aria-expanded={panelOpen}
		aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
		aria-describedby={error ? errorId : undefined}
		aria-invalid={error ? 'true' : undefined}
	/>
	<Popover.Root bind:open={getOpen, setOpen}>
		<Popover.Content
			customAnchor={inputEl}
			align="start"
			sideOffset={4}
			trapFocus={false}
			onOpenAutoFocus={(event) => event.preventDefault()}
			onCloseAutoFocus={(event) => event.preventDefault()}
			class="w-(--bits-popover-anchor-width) p-0"
		>
			<Command.Root shouldFilter={false} bind:value={commandValue} class="rounded-md! p-1">
				{#if loading}
					<div class="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground">
						<Spinner class="size-4" />
						{m.institution_searching()}
					</div>
				{:else if results.length > 0}
					<Command.List id={listboxId}>
						{#each results as institution, index (institution.id)}
							<Command.Item
								id={`${listboxId}-${index}`}
								value={String(institution.id)}
								class="flex-col items-start gap-0.5"
								onSelect={() => chooseInstitution(institution)}
							>
								<span class="font-semibold">{institution.label}</span>
								{#if institution.shortName || institution.code || institution.location}
									<span class="text-xs text-muted-foreground">
										{[institution.shortName, institution.code, institution.location]
											.filter(Boolean)
											.join(' · ')}
									</span>
								{/if}
							</Command.Item>
						{/each}
					</Command.List>
				{:else}
					<div class="flex flex-wrap items-center justify-between gap-3 p-2">
						<p class="text-sm text-muted-foreground">{m.institution_no_matches()}</p>
						<button
							type="button"
							class="text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-offset-2 focus-visible:outline-ring"
							onclick={chooseCustomLabel}
						>
							{m.institution_use_custom({ label: query })}
						</button>
					</div>
				{/if}
			</Command.Root>
		</Popover.Content>
	</Popover.Root>
	{#if error}
		<Field.Error id={errorId}>{error}</Field.Error>
	{/if}
</Field.Field>
