import type { PaymentState, RegistrationStatus } from '$lib/api/types';
import * as m from '$lib/paraglide/messages';

export function paymentStatusMessage(
	state: PaymentState,
	expired: boolean,
	status: RegistrationStatus
): string {
	if (expired || status === 'EXPIRED' || status === 'REJECTED') return m.payment_expired();
	switch (state) {
		case 'PENDING':
			return m.payment_pending_review();
		case 'VERIFIED':
			return m.payment_verified_review();
		case 'NOT_REQUIRED':
			return m.payment_free();
		case 'REJECTED':
			return m.payment_proof_rejected();
		case 'UNPAID':
			return m.payment_unpaid();
	}
}
