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
const turnstileTokens = vi.hoisted(() => ({ 'payment-proof-submit': 'payment-proof-submit-token' }));

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_TURNSTILE_SITE_KEY: 'site-key' } }));

vi.mock('$lib/api/registrations', () => ({ submitPaymentAttempt: vi.fn() }));

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	vi.mocked(submitPaymentAttempt).mockReset();
	turnstileTokens['payment-proof-submit'] = 'payment-proof-submit-token';
	document.head.querySelectorAll('script[data-turnstile-api]').forEach((script) => script.remove());
	const turnstileScript = document.createElement('script');
	turnstileScript.dataset.turnstileApi = 'true';
	document.head.appendChild(turnstileScript);
	window.turnstile = {
		render: (_container, options) => {
			options.callback(turnstileTokens[options.action as keyof typeof turnstileTokens] ?? '');
			return 'widget-id';
		}
	};
});

describe('RosterEditor', () => {
	it('renders one required, empty captain row for a solo game', () => {
		const { container } = render(RosterEditor, {
			teamSizeMin: 1,
			teamSizeMax: 1
		});

		expect(container.querySelectorAll('[data-roster-row]')).toHaveLength(1);
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toHaveValue('');
		expect(container.querySelector('input[name="member-1-school"]')).toHaveValue('');
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toBeRequired();
		expect(container.querySelector('input[name="member-1-school"]')).toBeRequired();
		expect(container.querySelector('input[name="member-1-gamer-tag"]')).toHaveAttribute(
			'data-slot',
			'input'
		);
		expect(container.querySelector('[role="radio"]')).toHaveAttribute('aria-checked', 'true');
	});

	it('renders the fixed team size with empty members and moves the only captain marker', async () => {
		let members: import('$lib/api/types').RegistrationMemberInput[] = [];
		const { container } = render(RosterEditor, {
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
				school_snapshot: '',
				is_captain: true,
				display_order: 1
			},
			{
				gamer_tag_snapshot: '',
				school_snapshot: '',
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
		await firstMember.getByLabelText('School').fill('HCMUS');

		expect(members[0]).toMatchObject({
			gamer_tag_snapshot: 'captain',
			school_snapshot: 'HCMUS'
		});
		expect(memberUpdates).toBe(2);
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
		const [token, registrationId, formData, turnstileToken] = vi.mocked(submitPaymentAttempt).mock.calls[0];
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
	it('submits a reference without requiring a proof file', async () => {
		vi.mocked(submitPaymentAttempt).mockResolvedValue({
			id: 5,
			status: 'PENDING',
			amount: '50000.00',
			currency: 'VND',
			created_at: '2026-07-19T00:00:00Z'
		});
		const onSuccess = vi.fn();
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess
		});

		await page.getByLabelText('Payment reference').fill('bank-transfer-12');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(submitPaymentAttempt).toHaveBeenCalledOnce());
		const formData = vi.mocked(submitPaymentAttempt).mock.calls[0][2];
		expect(formData.get('reference')).toBe('bank-transfer-12');
		expect(onSuccess).toHaveBeenCalledOnce();
	});

	it('requires either a proof file or a payment reference', async () => {
		render(PaymentAttemptForm, {
			registrationId: 12,
			accessToken: 'access-token',
			initialAmount: '50000.00',
			initialCurrency: 'VND',
			onSuccess: vi.fn()
		});

		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await expect
			.element(page.getByText('Provide a payment proof or reference.'))
			.toBeInTheDocument();
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

		await page.getByLabelText('Payment reference').fill('bank-transfer-12');
		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await expect.element(page.getByText(m.turnstile_required())).toBeVisible();
		expect(submitPaymentAttempt).not.toHaveBeenCalled();
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
		await page.getByLabelText('Payment reference').fill('bank-transfer-12');

		await page.getByRole('button', { name: 'Upload payment proof' }).click();

		await vi.waitFor(() => expect(onAuthenticationError).toHaveBeenCalledOnce());
	});
});
