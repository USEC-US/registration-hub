<script lang="ts">
	import { submitPaymentAttempt } from '$lib/api/registrations';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import * as m from '$lib/paraglide/messages';

	interface Props {
		registrationId: number;
		accessToken: string;
		initialAmount: string;
		initialCurrency: string;
		onSuccess: () => void | Promise<void>;
	}

	let { registrationId, accessToken, initialAmount, initialCurrency, onSuccess }: Props = $props();
	let amount = $state('');
	let currency = $state('');
	let reference = $state('');
	let submitting = $state(false);
	let formErrors = $state<string[]>([]);

	function initializePaymentFields(): void {
		amount = initialAmount;
		currency = initialCurrency;
	}

	initializePaymentFields();

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting) return;
		submitting = true;
		formErrors = [];

		try {
			const formData = new FormData(event.currentTarget as HTMLFormElement);
			await submitPaymentAttempt(accessToken, registrationId, formData);
			await onSuccess();
		} catch (cause) {
			({ formErrors } = formErrorsFrom(cause, m.payment_upload_failed()));
		} finally {
			submitting = false;
		}
	}
</script>

<section class="border border-[var(--line)]" aria-labelledby="payment-attempt-heading">
	<header class="border-b border-[var(--line)] bg-[var(--surface-muted)] p-5">
		<h2 class="font-heading text-xl font-semibold" id="payment-attempt-heading">
			{m.payment_attempt_heading()}
		</h2>
		<p class="mt-2 text-sm text-[var(--text-muted)]">{m.payment_attempt_intro()}</p>
	</header>
	<form class="grid gap-5 p-5" aria-busy={submitting} onsubmit={handleSubmit}>
		<ErrorSummary errors={formErrors} />
		<div class="grid gap-5 sm:grid-cols-2">
			<label class="grid gap-2 text-sm font-semibold">
				{m.field_payment_amount()}
				<input
					class="min-h-11 border border-[var(--line)] bg-white px-3 py-2 font-normal"
					name="amount"
					inputmode="decimal"
					required
					bind:value={amount}
				/>
			</label>
			<label class="grid gap-2 text-sm font-semibold">
				{m.field_payment_currency()}
				<input
					class="min-h-11 border border-[var(--line)] bg-white px-3 py-2 font-normal uppercase"
					name="currency"
					required
					maxlength="3"
					bind:value={currency}
				/>
			</label>
		</div>
		<label class="grid gap-2 text-sm font-semibold">
			{m.field_payment_proof()}
			<input
				class="min-h-11 border border-[var(--line)] bg-white px-3 py-2 font-normal"
				type="file"
				name="proof_file"
				accept="image/*,.pdf"
			/>
		</label>
		<label class="grid gap-2 text-sm font-semibold">
			{m.field_payment_reference()}
			<input
				class="min-h-11 border border-[var(--line)] bg-white px-3 py-2 font-normal"
				name="reference"
				maxlength="128"
				required
				bind:value={reference}
			/>
		</label>
		<div class="flex justify-end border-t border-[var(--line)] pt-5">
			<button
				class="min-h-11 border border-[var(--accent)] bg-[var(--accent)] px-5 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60"
				type="submit"
				disabled={submitting}
			>
				{submitting ? m.payment_uploading() : m.action_upload_payment_proof()}
			</button>
		</div>
	</form>
</section>
