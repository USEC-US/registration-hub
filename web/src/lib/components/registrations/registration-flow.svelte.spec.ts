import { fromStore, writable } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { ApiRequestError } from '$lib/api/client';
import { submitPaymentAttempt } from '$lib/api/registrations';
import type { RegistrationMemberInput } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import * as m from '$lib/paraglide/messages';
import PaymentAttemptForm from './PaymentAttemptForm.svelte';
import RosterEditor from './RosterEditor.svelte';
const turnstileTokens = vi.hoisted(() => ({
	'payment-proof-submit': 'payment-proof-submit-token'
}));
const turnstileReset = vi.hoisted(() => vi.fn());

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_TURNSTILE_SITE_KEY: 'site-key' } }));

vi.mock('$lib/api/institutions', () => ({ searchInstitutions: vi.fn().mockResolvedValue([]) }));

vi.mock('$lib/api/registrations', () => ({ submitPaymentAttempt: vi.fn() }));

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	vi.mocked(submitPaymentAttempt).mockReset();
	turnstileTokens['payment-proof-submit'] = 'payment-proof-submit-token';
	turnstileReset.mockReset();
	document.head.querySelectorAll('script[data-turnstile-api]').forEach((script) => script.remove());
	const turnstileScript = document.createElement('script');
	turnstileScript.dataset.turnstileApi = 'true';
	document.head.appendChild(turnstileScript);
	window.turnstile = {
		render: (_container, options) => {
			options.callback(turnstileTokens[options.action as keyof typeof turnstileTokens] ?? '');
			return 'widget-id';
		},
		reset: turnstileReset
	};
});

describe('RosterEditor', () => {
	it('retains each institution selection when a preceding optional row is removed', async () => {
		const state = fromStore(writable<RegistrationMemberInput[]>([]));
		render(RosterEditor, {
			teamSizeMin: 1,
			teamSizeMax: 3,
			get members() {
				return state.current;
			},
			set members(value) {
				state.current = value;
			}
		});
		await page.getByRole('button', { name: 'Add player', exact: true }).click();
		await page.getByRole('button', { name: 'Add player', exact: true }).click();
		for (let index = 0; index < 3; index++) {
			await page.getByRole('combobox', { name: 'Institution' }).nth(index).fill(`School ${index}`);
			await page.getByRole('button', { name: `Use "School ${index}"` }).click();
		}
		await expect
			.element(page.getByRole('button', { name: 'Remove member 1', exact: true }))
			.toBeDisabled();
		await page.getByRole('button', { name: 'Remove member 2', exact: true }).click();
		await expect
			.element(page.getByRole('combobox', { name: 'Institution' }).nth(1))
			.toHaveValue('School 2');
		expect(state.current[1]).toMatchObject({ institution_label: 'School 2', display_order: 2 });
	});

	it('starts at the minimum and supports adding and removing optional players', async () => {
		const state = fromStore(writable<RegistrationMemberInput[]>([]));
		const { container } = render(RosterEditor, {
			submitterRole: 'manager',
			teamSizeMin: 2,
			teamSizeMax: 3,
			get members() {
				return state.current;
			},
			set members(value) {
				state.current = value;
			}
		});
		expect(container.querySelectorAll('[data-roster-row]')).toHaveLength(2);
		await expect
			.element(page.getByRole('button', { name: 'Remove member 1', exact: true }))
			.toBeDisabled();
		await page.getByRole('button', { name: 'Add player', exact: true }).click();
		await expect
			.element(page.getByRole('button', { name: 'Add player', exact: true }))
			.toBeDisabled();
		await page.getByRole('radio', { name: 'Set member 3 as captain' }).click();
		await page
			.getByRole('group', { name: 'Roster member 2', exact: true })
			.getByLabelText('Gamer tag')
			.fill('retained');
		await page.getByRole('button', { name: 'Remove member 3', exact: true }).click();
		expect(state.current).toHaveLength(2);
		expect(state.current.map((member) => member.display_order)).toEqual([1, 2]);
		expect(state.current[1].gamer_tag_snapshot).toBe('retained');
		expect(state.current.filter((member) => member.is_captain)).toHaveLength(1);
		expect(state.current[0].is_captain).toBe(true);
	});
	it('renders one required, empty captain row for a solo game', () => {
		const { container } = render(RosterEditor, {
			teamSizeMin: 1,
			teamSizeMax: 1
		});

		expect(container.querySelectorAll('[data-roster-row]')).toHaveLength(1);
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toHaveValue('');
		expect(container.querySelector('input[name="institution"]')).toHaveValue('');
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toBeRequired();
		expect(container.querySelector('input[name="institution"]')).toBeRequired();
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toHaveAttribute(
			'data-slot',
			'input'
		);
		expect(container.querySelector('[role="radio"]')).toHaveAttribute('aria-checked', 'true');
	});

	it('renders the fixed team size with empty members and moves the only captain marker', async () => {
		let members: import('$lib/api/types').RegistrationMemberInput[] = [];
		const { container } = render(RosterEditor, {
			submitterRole: 'manager',
			teamSizeMin: 2,
			teamSizeMax: 2,
			get members() {
				return members;
			},
			set members(value) {
				members = value;
			}
		});
		expect(members).toEqual([
			{
				gamer_tag_snapshot: '',
				institution_label: '',
				is_captain: true,
				display_order: 1
			},
			{
				gamer_tag_snapshot: '',
				institution_label: '',
				is_captain: false,
				display_order: 2
			}
		]);
		expect(container.querySelectorAll('[data-roster-row]')).toHaveLength(2);
		const captain = page.getByRole('radio', { name: 'Set member 2 as captain' });
		await expect.element(captain).toHaveAttribute('data-slot', 'radio-group-item');
		await captain.click();

		const controls = container.querySelectorAll<HTMLElement>('[role="radio"]');
		expect(controls[0]).toHaveAttribute('aria-checked', 'false');
		expect(controls[1]).toHaveAttribute('aria-checked', 'true');
		expect(
			Array.from(controls).filter((control) => control.getAttribute('aria-checked') === 'true')
		).toHaveLength(1);
	});

	it('propagates text edits through the bound members array', async () => {
		let members: RegistrationMemberInput[] = [];
		let memberUpdates = 0;
		render(RosterEditor, {
			submitterRole: 'manager',
			teamSizeMin: 2,
			teamSizeMax: 2,
			get members() {
				return members;
			},
			set members(value) {
				members = value;
				memberUpdates += 1;
			}
		});
		memberUpdates = 0;

		const firstMember = page.getByRole('group', { name: 'Roster member 1' });
		await firstMember.getByLabelText('Gamer tag').fill('captain');
		await firstMember.getByRole('combobox', { name: 'Institution' }).fill('HCMUS');
		await page.getByRole('button', { name: 'Use "HCMUS"' }).click();

		expect(members[0]).toMatchObject({
			gamer_tag_snapshot: 'captain',
			institution_label: 'HCMUS'
		});
		expect(memberUpdates).toBeGreaterThanOrEqual(2);
	});
});

function attachProof(file = new File(['proof'], 'proof.png', { type: 'image/png' })): void {
	const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
	const transfer = new DataTransfer();
	transfer.items.add(file);
	input.files = transfer.files;
	input.dispatchEvent(new Event('change', { bubbles: true }));
}

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
		expect(container.querySelector('[data-slot="card"]')).not.toBeNull();
		expect(container.querySelector('button[type="submit"]')).toHaveAttribute('data-slot', 'button');

		const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
		expect(fileInput).not.toBeNull();
		const transfer = new DataTransfer();
		transfer.items.add(new File(['proof'], 'proof.png', { type: 'image/png' }));
		if (fileInput) fileInput.files = transfer.files;
		fileInput?.dispatchEvent(new Event('change', { bubbles: true }));
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(submitPaymentAttempt).toHaveBeenCalledOnce());
		const [token, registrationId, formData, turnstileToken] =
			vi.mocked(submitPaymentAttempt).mock.calls[0];
		expect(token).toBe('access-token');
		expect(registrationId).toBe(12);
		expect(formData.get('amount')).toBe('50000.00');
		expect(formData.get('currency')).toBe('VND');
		expect(formData.get('reference')).toBe('');
		expect(formData.get('proof_file')).toBeInstanceOf(File);
		expect(turnstileToken).toBe('payment-proof-submit-token');
		expect(onSuccess).toHaveBeenCalledOnce();
	});

	it('shows a disabled generated action while payment submission is pending', async () => {
		let resolveUpload!: () => void;
		vi.mocked(submitPaymentAttempt).mockReturnValue(
			new Promise((resolve) => {
				resolveUpload = () =>
					resolve({
						id: 4,
						status: 'PENDING',
						amount: '50000.00',
						currency: 'VND',
						created_at: '2026-07-19T00:00:00Z'
					});
			})
		);
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});

		attachProof();
		await page.getByLabelText('Payment reference').fill('bank-transfer-12');
		const button = page
			.getByRole('button', { name: 'Upload payment proof' })
			.elements()[0] as HTMLButtonElement;
		button.click();

		await vi.waitFor(() => expect(submitPaymentAttempt).toHaveBeenCalledOnce());
		expect(button).toBeDisabled();
		expect(button).toHaveAttribute('data-slot', 'button');
		expect(button.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
		resolveUpload();
	});
	it('rejects a reference without an image', async () => {
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});
		await page.getByLabelText('Payment reference').fill('bank-transfer-12');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();
		await expect.element(page.getByText(m.payment_evidence_required())).toBeVisible();
		expect(submitPaymentAttempt).not.toHaveBeenCalled();
	});

	it.each([
		new File(['pdf'], 'proof.pdf', { type: 'application/pdf' }),
		new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'proof.png', { type: 'image/png' })
	])('rejects unsupported or oversized files before submission', async (file) => {
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});
		attachProof(file);
		await page.getByRole('button', { name: 'Upload payment proof' }).click();
		await expect.element(page.getByText(m.payment_image_invalid())).toBeVisible();
		expect(submitPaymentAttempt).not.toHaveBeenCalled();
	});

	it('requires a proof image', async () => {
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});

		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await expect.element(page.getByText(m.payment_evidence_required())).toBeInTheDocument();
		expect(submitPaymentAttempt).not.toHaveBeenCalled();
	});

	it('requires Turnstile before uploading payment evidence', async () => {
		turnstileTokens['payment-proof-submit'] = '';
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});

		attachProof();
		await page.getByLabelText('Payment reference').fill('bank-transfer-12');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await expect.element(page.getByText(m.turnstile_required())).toBeVisible();
		expect(submitPaymentAttempt).not.toHaveBeenCalled();
	});

	it('requires a fresh Turnstile callback before retrying payment proof upload', async () => {
		vi.mocked(submitPaymentAttempt).mockRejectedValue(new Error('Request failed.'));
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});

		attachProof();
		await page.getByLabelText('Payment reference').fill('bank-transfer-12');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(submitPaymentAttempt).toHaveBeenCalledOnce());
		expect(turnstileReset).toHaveBeenCalledWith('widget-id');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await expect.element(page.getByText(m.turnstile_required())).toBeVisible();
		expect(submitPaymentAttempt).toHaveBeenCalledOnce();
	});

	it('shows serializer field errors in the summary', async () => {
		vi.mocked(submitPaymentAttempt).mockRejectedValue(
			new ApiRequestError(400, 'Request failed.', { amount: ['Enter a valid amount.'] })
		);
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});
		attachProof();
		await page.getByLabelText('Payment reference').fill('bank-transfer-12');

		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await expect.element(page.getByText('Enter a valid amount.')).toBeInTheDocument();
	});

	it('delegates expired-session handling to the parent page', async () => {
		vi.mocked(submitPaymentAttempt).mockRejectedValue(
			new ApiRequestError(401, 'Session expired.', {}, [], 'Session expired.')
		);
		const onAuthenticationError = vi.fn();
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn(),
			onAuthenticationError
		});
		attachProof();
		await page.getByLabelText('Payment reference').fill('bank-transfer-12');

		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(onAuthenticationError).toHaveBeenCalledOnce());
	});
});
