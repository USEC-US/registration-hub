<script lang="ts">
	import { ApiRequestError } from '$lib/api/client';
	import { submitPaymentAttempt } from '$lib/api/registrations';
	import ErrorSummary from '$lib/components/forms/ErrorSummary.svelte';
	import TurnstileWidget from '$lib/components/forms/TurnstileWidget.svelte';
	import PaymentProofField from './PaymentProofField.svelte';
	import PaymentReferenceField from './PaymentReferenceField.svelte';
	import { formErrorsFrom } from '$lib/forms/api-errors';
	import * as m from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Card from '$lib/components/ui/card';
	import * as Field from '$lib/components/ui/field';
	import { Input } from '$lib/components/ui/input';
	import { Spinner } from '$lib/components/ui/spinner';

	interface Props {
		registrationId: number;
		accessToken: string;
		initialAmount: string;
		initialCurrency: string;
		paymentReference?: string;
		onSuccess: () => void | Promise<void>;
		onAuthenticationError?: () => void | Promise<void>;
	}

	let {
		registrationId,
		accessToken,
		initialAmount,
		initialCurrency,
		paymentReference = '',
		onSuccess,
		onAuthenticationError = () => {}
	}: Props = $props();
	let amount = $state('');
	let currency = $state('');
	let referenceReady = $state(false);
	let proofFile = $state<File | undefined>();
	let proofSelectionError = $state('');
	let turnstileToken = $state('');
	let turnstileWidget = $state<{ reset: () => void } | null>(null);
	let submitting = $state(false);
	let formErrors = $state<string[]>([]);

	function initializePaymentFields(): void {
		amount = initialAmount;
		currency = initialCurrency;
	}

	initializePaymentFields();

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting || proofSelectionError || !referenceReady) return;

		const formData = new FormData(event.currentTarget as HTMLFormElement);
		if (proofFile) formData.set('proof_file', proofFile);
		if (!proofFile || proofFile.size === 0) {
			formErrors = [m.payment_evidence_required()];
			return;
		}
		if (
			proofFile.size > 10 * 1024 * 1024 ||
			!['image/jpeg', 'image/png', 'image/webp'].includes(proofFile.type)
		) {
			formErrors = [m.payment_image_invalid()];
			return;
		}
		if (!turnstileToken) {
			formErrors = [m.turnstile_required()];
			return;
		}

		submitting = true;
		formErrors = [];

		try {
			const request = submitPaymentAttempt(accessToken, registrationId, formData, turnstileToken);
			turnstileWidget?.reset();
			await request;
			await onSuccess();
		} catch (cause) {
			if (cause instanceof ApiRequestError && cause.status === 401) {
				await onAuthenticationError();
				return;
			}
			const nextErrors = formErrorsFrom(cause, m.payment_upload_failed());
			formErrors = [...nextErrors.formErrors, ...Object.values(nextErrors.fieldErrors).flat()];
		} finally {
			submitting = false;
		}
	}
</script>

<Card.Root aria-labelledby="payment-attempt-heading">
	<Card.Header>
		<Card.Title role="heading" aria-level={2} id="payment-attempt-heading">
			{m.payment_attempt_heading()}
		</Card.Title>
		<Card.Description>{m.payment_attempt_intro()}</Card.Description>
	</Card.Header>
	<form aria-busy={submitting} onsubmit={handleSubmit}>
		<Card.Content>
			<ErrorSummary errors={formErrors} />
			<Field.Group class="gap-5">
				<Field.Group class="gap-5 sm:grid sm:grid-cols-2">
					<Field.Field>
						<Field.Label for="amount">{m.field_payment_amount()}</Field.Label>
						<Input id="amount" name="amount" inputmode="decimal" required bind:value={amount} />
					</Field.Field>
					<Field.Field>
						<Field.Label for="currency">{m.field_payment_currency()}</Field.Label>
						<Input id="currency" name="currency" required maxlength={3} bind:value={currency} />
					</Field.Field>
				</Field.Group>
				<PaymentProofField
					required
					disabled={submitting}
					bind:file={proofFile}
					bind:selectionError={proofSelectionError}
				/>
				<PaymentReferenceField
					bind:ready={referenceReady}
					{registrationId}
					{accessToken}
					initialReference={paymentReference}
					{amount}
					{currency}
				/>
				<TurnstileWidget
					bind:this={turnstileWidget}
					action="payment-proof-submit"
					bind:token={turnstileToken}
				/>
			</Field.Group>
		</Card.Content>
		<Card.Footer class="justify-end border-t">
			<Button class="min-h-11" type="submit" disabled={submitting || !referenceReady}>
				{#if submitting}<Spinner aria-hidden="true" />{/if}
				{submitting ? m.payment_uploading() : m.action_upload_payment_proof()}
			</Button>
		</Card.Footer>
	</form>
</Card.Root>
