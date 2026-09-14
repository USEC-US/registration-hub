import { beforeEach, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { fromStore, writable } from 'svelte/store';
import { reservePaymentReference } from '$lib/api/registrations';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import PaymentReferenceField from './PaymentReferenceField.svelte';

vi.mock('$lib/api/registrations', () => ({
	reservePaymentReference: vi.fn(),
	getPaymentReference: vi.fn()
}));
const intent = {
	token: 'private-token',
	reference: 'USEC23456789AB',
	amount: '50000.00',
	currency: 'VND'
};
beforeEach(() => {
	overwriteGetLocale(() => 'en');
	sessionStorage.clear();
	vi.mocked(reservePaymentReference).mockReset().mockResolvedValue(intent);
});
it('displays a read-only reference and resumes its private token on reload', async () => {
	const state = fromStore(writable(''));
	const props = {
		gameId: 10,
		amount: '50000.00',
		currency: 'VND',
		get token() {
			return state.current;
		},
		set token(token: string) {
			state.current = token;
		}
	};
	const first = render(PaymentReferenceField, props);
	await expect.element(page.getByLabelText('Payment reference')).toHaveValue(intent.reference);
	await expect.element(page.getByLabelText('Payment reference')).toHaveAttribute('readonly');
	expect(state.current).toBe(intent.token);
	expect(sessionStorage.getItem('usec-payment-intent:10')).toBe(intent.token);
	await first.unmount();
	render(PaymentReferenceField, props);
	await expect.element(page.getByLabelText('Payment reference')).toHaveValue(intent.reference);
	expect(reservePaymentReference).toHaveBeenLastCalledWith(10, intent.token);
});
it('preserves an issued reference and blocks submission when the fee changes', async () => {
	const state = fromStore(writable(''));
	render(PaymentReferenceField, {
		gameId: 10,
		amount: '60000.00',
		currency: 'VND',
		get token() {
			return state.current;
		},
		set token(token: string) {
			state.current = token;
		}
	});
	await expect.element(page.getByText(/The registration fee has changed/)).toBeVisible();
	await expect.element(page.getByLabelText('Payment reference')).toHaveValue(intent.reference);
	expect(state.current).toBe('');
	expect(sessionStorage.getItem('usec-payment-intent:10')).toBe(intent.token);
});
it('retries failed initialization with the existing token instead of silently replacing it', async () => {
	sessionStorage.setItem('usec-payment-intent:10', intent.token);
	vi.mocked(reservePaymentReference).mockRejectedValueOnce(new Error('Network unavailable'));
	render(PaymentReferenceField, { gameId: 10, amount: '50000.00', currency: 'VND' });
	await page.getByRole('button', { name: 'Retry', exact: true }).click();
	await expect.element(page.getByLabelText('Payment reference')).toHaveValue(intent.reference);
	expect(reservePaymentReference).toHaveBeenLastCalledWith(10, intent.token);
});
