<script lang="ts">
	import * as Field from '$lib/components/ui/field';
	import * as FileDropZone from '$lib/components/ui/file-drop-zone';
	import { Button } from '$lib/components/ui/button';
	import Upload from '@lucide/svelte/icons/upload';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import * as m from '$lib/paraglide/messages';

	let {
		file = $bindable<File | undefined>(),
		selectionError = $bindable(''),
		required = false,
		disabled = false,
		error
	}: {
		file?: File;
		selectionError?: string;
		required?: boolean;
		disabled?: boolean;
		error?: string;
	} = $props();

	const id = $props.id();
	const inputId = `${id}-proof`;
	const hintId = `${id}-hint`;
	const errorId = `${id}-error`;
	let rejectedBatch = false;
	let previewUrl = $state('');
	const displayError = $derived(selectionError || error);
	const describedBy = $derived([hintId, displayError ? errorId : ''].filter(Boolean).join(' '));

	$effect(() => {
		if (!file) {
			previewUrl = '';
			return;
		}
		const url = URL.createObjectURL(file);
		previewUrl = url;
		return () => URL.revokeObjectURL(url);
	});

	function rejectFile({ reason }: { reason: FileDropZone.FileRejectedReason }): void {
		rejectedBatch = true;
		file = undefined;
		selectionError =
			reason === 'Maximum files uploaded' ? m.payment_image_single() : m.payment_image_invalid();
	}

	async function selectFiles(files: File[]): Promise<void> {
		// Reject the whole selection if any file failed, including multi-file drops.
		if (rejectedBatch) {
			rejectedBatch = false;
			return;
		}
		if (!files.length) return;
		if (!files[0].size) {
			file = undefined;
			selectionError = m.payment_image_invalid();
			return;
		}
		file = files[0];
		selectionError = '';
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (!disabled && (event.key === 'Enter' || event.key === ' ')) {
			event.preventDefault();
			document.getElementById(inputId)?.click();
		}
	}

	function removeFile(): void {
		file = undefined;
		selectionError = '';
	}
</script>

<Field.Field data-invalid={!!displayError}>
	<Field.Label for={inputId}>{m.field_payment_proof()}</Field.Label>
	<FileDropZone.Root
		id={inputId}
		name="proof_file"
		accept="image/jpeg,image/png,image/webp"
		maxFiles={1}
		fileCount={0}
		maxFileSize={10 * 1024 * 1024}
		{disabled}
		aria-label={m.field_payment_proof()}
		aria-required={required}
		aria-invalid={!!displayError}
		aria-describedby={describedBy}
		onUpload={selectFiles}
		onFileRejected={rejectFile}
	>
		<FileDropZone.Trigger
			data-payment-proof-drop-zone
			role="button"
			tabindex={disabled ? -1 : 0}
			aria-label={file ? m.payment_image_replace() : m.payment_image_choose()}
			aria-describedby={describedBy}
			onkeydown={handleKeydown}
			class="flex min-h-44 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-5 text-center transition-colors hover:border-primary/50 hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:pointer-events-none aria-disabled:opacity-50"
		>
			{#if file && previewUrl}
				<img
					src={previewUrl}
					alt={m.payment_image_preview()}
					class="max-h-52 max-w-full rounded-md object-contain"
				/>
			{:else}
				<Upload class="size-7 text-muted-foreground" aria-hidden="true" />
			{/if}
			<span class="text-sm font-medium">{m.payment_image_drop()}</span>
			<span class="text-sm font-semibold text-primary underline underline-offset-4">
				{file ? m.payment_image_replace() : m.payment_image_choose()}
			</span>
		</FileDropZone.Trigger>
	</FileDropZone.Root>
	{#if file}
		<div class="flex min-w-0 items-center justify-between gap-3 rounded-lg border px-4 py-3">
			<p class="min-w-0 break-all text-sm" role="status">{file.name}</p>
			<Button
				type="button"
				variant="ghost"
				size="icon"
				{disabled}
				aria-label={m.payment_image_remove()}
				onclick={removeFile}
			>
				<Trash2 aria-hidden="true" />
			</Button>
		</div>
	{:else if selectionError}
		<Button type="button" variant="ghost" class="w-fit" {disabled} onclick={removeFile}>
			<Trash2 data-icon="inline-start" aria-hidden="true" />{m.payment_image_remove()}
		</Button>
	{/if}
	<Field.Description id={hintId}>{m.payment_image_hint()}</Field.Description>
	{#if displayError}<Field.Error id={errorId} role="alert">{displayError}</Field.Error>{/if}
</Field.Field>
