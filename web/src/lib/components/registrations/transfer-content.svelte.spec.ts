import { beforeEach, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { fromStore, writable } from 'svelte/store';
import { reservePaymentInstructions } from '$lib/api/registrations';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import TransferContentField from './TransferContentField.svelte';

vi.mock('$lib/api/registrations', () => ({
	reservePaymentInstructions: vi.fn(),
	getPaymentInstructions: vi.fn()
}));
const intent = {
	token: 'private-token',
	transfer_content_template: '{participant} thanh toan le phi Summer',
	transfer_content_limit: 100,
	amount: '50000.00',
	currency: 'VND'
};
beforeEach(() => {
	overwriteGetLocale(() => 'en');
	sessionStorage.clear();
	vi.mocked(reservePaymentInstructions).mockReset().mockResolvedValue(intent);
});
it('displays accent-free transfer content and resumes its private token on reload', async () => {
	const state = fromStore(writable(''));
	const props = {
		gameId: 10,
		participant: 'Đặng#VN',
		amount: '50000.00',
		currency: 'VND',
		get token() {
			return state.current;
		},
		set token(token: string) {
			state.current = token;
		}
	};
	const first = render(TransferContentField, props);
	await expect
		.element(page.getByLabelText('Transfer content'))
		.toHaveTextContent('Dang#VN thanh toan le phi Summer');
	await expect.element(page.getByLabelText('Transfer content')).toHaveProperty('tagName', 'OUTPUT');
	await expect.poll(() => state.current).toBe(intent.token);
	await expect.element(page.getByLabelText('Payment reference')).not.toBeInTheDocument();
	expect(sessionStorage.getItem('usec-payment-intent:10')).toBe(intent.token);
	await first.unmount();
	render(TransferContentField, props);
	await expect
		.element(page.getByLabelText('Transfer content'))
		.toHaveTextContent('Dang#VN thanh toan le phi Summer');
	expect(reservePaymentInstructions).toHaveBeenLastCalledWith(10, intent.token);
});
it('preserves issued instructions and blocks submission when the fee changes', async () => {
	const state = fromStore(writable(''));
	render(TransferContentField, {
		gameId: 10,
		participant: 'Đặng#VN',
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
	await expect
		.element(page.getByLabelText('Transfer content'))
		.toHaveTextContent('Dang#VN thanh toan le phi Summer');
	expect(state.current).toBe('');
	expect(sessionStorage.getItem('usec-payment-intent:10')).toBe(intent.token);
});
it('retries failed initialization with the existing token instead of silently replacing it', async () => {
	sessionStorage.setItem('usec-payment-intent:10', intent.token);
	vi.mocked(reservePaymentInstructions).mockRejectedValueOnce(new Error('Network unavailable'));
	render(TransferContentField, {
		gameId: 10,
		participant: 'Đặng#VN',
		amount: '50000.00',
		currency: 'VND'
	});
	await page.getByRole('button', { name: 'Retry', exact: true }).click();
	await expect
		.element(page.getByLabelText('Transfer content'))
		.toHaveTextContent('Dang#VN thanh toan le phi Summer');
	expect(reservePaymentInstructions).toHaveBeenLastCalledWith(10, intent.token);
});

it('updates transfer text as the participant changes and blocks overlong content', async () => {
	const participant = fromStore(writable('ABC'));
	const ready = fromStore(writable(false));
	render(TransferContentField, {
		gameId: 10,
		amount: '50000.00',
		currency: 'VND',
		get participant() {
			return participant.current;
		},
		get ready() {
			return ready.current;
		},
		set ready(value: boolean) {
			ready.current = value;
		}
	});
	await expect
		.element(page.getByLabelText('Transfer content'))
		.toHaveTextContent('ABC thanh toan le phi Summer');
	await expect.poll(() => ready.current).toBe(true);
	participant.current = 'Đặng Văn#VN';
	await expect
		.element(page.getByLabelText('Transfer content'))
		.toHaveTextContent('Dang Van#VN thanh toan le phi Summer');
	participant.current = 'A'.repeat(100);
	await expect
		.element(
			page.getByText(
				'Transfer content exceeds 100 characters. Contact the organizers for shorter instructions.'
			)
		)
		.toBeVisible();
	await expect.element(page.getByRole('button', { name: 'Copy', exact: true })).toBeDisabled();
	await expect.poll(() => ready.current).toBe(false);
});
