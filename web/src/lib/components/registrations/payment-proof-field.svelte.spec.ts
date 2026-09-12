import { fromStore, writable } from 'svelte/store';
import { beforeEach, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import PaymentProofField from './PaymentProofField.svelte';

beforeEach(() => overwriteGetLocale(() => 'en'));

function setup(disabled = false) {
	const state = fromStore(writable<File | undefined>());
	const view = render(PaymentProofField, {
		required: true,
		disabled,
		get file() {
			return state.current;
		},
		set file(value) {
			state.current = value;
		}
	});
	return { state, ...view };
}

function choose(container: HTMLElement, files: File[], drop = false) {
	const transfer = new DataTransfer();
	files.forEach((file) => transfer.items.add(file));
	if (drop) {
		container
			.querySelector('[data-payment-proof-drop-zone]')!
			.dispatchEvent(
				new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer })
			);
	} else {
		const input = container.querySelector<HTMLInputElement>('input[type=file]')!;
		input.files = transfer.files;
		input.dispatchEvent(new Event('change', { bubbles: true }));
	}
}

it('keeps picked and dropped images in state after the native input resets', async () => {
	const { state, container } = setup();
	const first = new File(['image'], 'first.png', { type: 'image/png' });
	choose(container, [first]);
	await expect.element(page.getByText('first.png', { exact: true })).toBeVisible();
	expect(state.current).toBe(first);
	expect(container.querySelector<HTMLInputElement>('input[type=file]')!.files).toHaveLength(0);
	const replacement = new File(['replacement'], 'replacement.webp', { type: 'image/webp' });
	choose(container, [replacement], true);
	await expect.element(page.getByText('replacement.webp', { exact: true })).toBeVisible();
	expect(state.current).toBe(replacement);
	await page.getByRole('button', { name: 'Remove image', exact: true }).click();
	expect(state.current).toBeUndefined();
	await expect
		.element(page.getByRole('button', { name: 'Choose image', exact: true }))
		.toBeVisible();
});

it.each([
	new File(['pdf'], 'proof.pdf', { type: 'application/pdf' }),
	new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' }),
	new File([], 'empty.png', { type: 'image/png' })
])('rejects an invalid image and clears the previous selection', async (invalid) => {
	const { state, container } = setup();
	choose(container, [new File(['image'], 'first.png', { type: 'image/png' })]);
	await expect.element(page.getByText('first.png', { exact: true })).toBeVisible();
	choose(container, [invalid], true);
	await expect
		.element(page.getByRole('alert'))
		.toHaveTextContent('Choose a JPEG, PNG, or WebP image no larger than 10 MB.');
	expect(state.current).toBeUndefined();
});

it('rejects a batch containing more than one image', async () => {
	const { state, container } = setup();
	choose(
		container,
		['one.png', 'two.png'].map((name) => new File(['image'], name, { type: 'image/png' })),
		true
	);
	await expect
		.element(page.getByRole('alert'))
		.toHaveTextContent('Choose one payment proof image at a time.');
	expect(state.current).toBeUndefined();
});

it('ignores dropped images while submitting', async () => {
	const { state, container } = setup(true);
	choose(container, [new File(['image'], 'proof.png', { type: 'image/png' })], true);
	expect(state.current).toBeUndefined();
	await expect
		.element(page.getByRole('button', { name: 'Choose image', exact: true }))
		.toHaveAttribute('aria-disabled', 'true');
});
