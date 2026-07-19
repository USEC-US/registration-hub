import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { submitPaymentAttempt } from '$lib/api/registrations';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import PaymentAttemptForm from './PaymentAttemptForm.svelte';
import RosterEditor from './RosterEditor.svelte';
vi.mock('$env/dynamic/public', () => ({ env: {} }));

vi.mock('$lib/api/registrations', () => ({ submitPaymentAttempt: vi.fn() }));

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	vi.mocked(submitPaymentAttempt).mockReset();
});

describe('RosterEditor', () => {
	it('renders one required, prefilled captain row for a solo game', () => {
		const { container } = render(RosterEditor, {
			teamSizeMin: 1,
			teamSizeMax: 1,
			initialGamerTag: 'rookie',
			initialSchool: 'HCMUS'
		});

		expect(container.querySelectorAll('[data-roster-row]')).toHaveLength(1);
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toHaveValue('rookie');
		expect(container.querySelector('input[name="member-1-school"]')).toHaveValue('HCMUS');
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toBeRequired();
		expect(container.querySelector('input[name="member-1-school"]')).toBeRequired();
		expect(container.querySelector('input[name="captain"]')).toBeChecked();
	});

	it('renders the fixed team size and moves the only captain marker', async () => {
		const { container } = render(RosterEditor, {
			teamSizeMin: 5,
			teamSizeMax: 5,
			initialGamerTag: 'captain',
			initialSchool: 'HCMUS'
		});

		expect(container.querySelectorAll('[data-roster-row]')).toHaveLength(5);
		await page.getByRole('radio', { name: 'Set member 3 as captain' }).click();

		const controls = container.querySelectorAll<HTMLInputElement>('input[name="captain"]');
		expect(controls[0]).not.toBeChecked();
		expect(controls[2]).toBeChecked();
		expect(Array.from(controls).filter((control) => control.checked)).toHaveLength(1);
	});
});

describe('PaymentAttemptForm', () => {
	it('uploads payment evidence as FormData and reports success', async () => {
		vi.mocked(submitPaymentAttempt).mockResolvedValue({
			id: 4,
			status: 'PENDING',
			amount: '50000.00',
			currency: 'VND',
			created_at: '2026-07-19T00:00:00Z'
		});
		const onSuccess = vi.fn();
		const { container } = render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess
		});

		await page.getByLabelText('Payment reference').fill('bank-transfer-12');
		const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
		expect(fileInput).not.toBeNull();
		const transfer = new DataTransfer();
		transfer.items.add(new File(['proof'], 'proof.png', { type: 'image/png' }));
		Object.defineProperty(fileInput, 'files', { value: transfer.files });
		fileInput?.dispatchEvent(new Event('change', { bubbles: true }));
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(submitPaymentAttempt).toHaveBeenCalledOnce());
		const [token, registrationId, formData] = vi.mocked(submitPaymentAttempt).mock.calls[0];
		expect(token).toBe('access-token');
		expect(registrationId).toBe(12);
		expect(formData.get('amount')).toBe('50000.00');
		expect(formData.get('currency')).toBe('VND');
		expect(formData.get('reference')).toBe('bank-transfer-12');
		expect(formData.get('proof_file')).toBeInstanceOf(File);
		expect(onSuccess).toHaveBeenCalledOnce();
	});
});
