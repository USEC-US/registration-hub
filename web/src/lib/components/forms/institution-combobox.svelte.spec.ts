import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { searchInstitutions } from '$lib/api/institutions';
import type { InstitutionChoice } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import InstitutionCombobox from './InstitutionCombobox.svelte';

vi.mock('$lib/api/institutions', () => ({ searchInstitutions: vi.fn() }));

const institution = {
	id: 7,
	value: '227',
	label: 'University of Science',
	code: 'QST',
	shortName: 'HCMUS',
	eng: 'University of Science',
	type: 'Public',
	location: 'Ho Chi Minh City'
};

beforeEach(() => {
	overwriteGetLocale(() => 'en');
	vi.mocked(searchInstitutions).mockReset();
});

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

it('selects a catalogue institution from search results', async () => {
	let choice: InstitutionChoice | undefined;
	vi.mocked(searchInstitutions).mockResolvedValue([institution]);
	render(InstitutionCombobox, {
		get choice() {
			return choice;
		},
		set choice(value) {
			choice = value;
		}
	});

	await page.getByLabelText('Institution').fill('science');
	await expect.element(page.getByRole('option', { name: /University of Science/ })).toBeVisible();
	await page.getByRole('option', { name: /University of Science/ }).click();

	expect(choice).toEqual({ institution_id: 7 });
});

it('uses a non-empty search label as a custom institution', async () => {
	let choice: InstitutionChoice | undefined;
	vi.mocked(searchInstitutions).mockResolvedValue([]);
	render(InstitutionCombobox, {
		get choice() {
			return choice;
		},
		set choice(value) {
			choice = value;
		}
	});

	await page.getByLabelText('Institution').fill('New Academy');
	await expect.element(page.getByRole('button', { name: 'Use "New Academy"' })).toBeVisible();
	await page.getByRole('button', { name: 'Use "New Academy"' }).click();

	expect(choice).toEqual({ institution_label: 'New Academy' });
});

it('selects the active search result with ArrowDown and Enter', async () => {
	let choice: InstitutionChoice | undefined;
	vi.mocked(searchInstitutions).mockResolvedValue([institution]);
	render(InstitutionCombobox, {
		get choice() {
			return choice;
		},
		set choice(value) {
			choice = value;
		}
	});

	const input = page.getByLabelText('Institution');
	await input.fill('science');
	await expect.element(page.getByRole('option', { name: /University of Science/ })).toBeVisible();
	const inputElement = input.elements()[0] as HTMLInputElement;
	inputElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
	inputElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

	expect(choice).toEqual({ institution_id: 7 });
});

it('removes stale result buttons before a new search debounce completes', async () => {
	vi.mocked(searchInstitutions).mockResolvedValue([institution]);
	render(InstitutionCombobox);

	const input = page.getByLabelText('Institution');
	await input.fill('science');
	await expect.element(page.getByRole('option', { name: /University of Science/ })).toBeVisible();
	await input.fill('new query');

	await expect
		.element(page.getByRole('option', { name: /University of Science/ }))
		.not.toBeInTheDocument();
});

it('does not choose a stale active result when Enter is pressed after changing the query', async () => {
	let choice: InstitutionChoice | undefined;
	vi.mocked(searchInstitutions).mockResolvedValue([institution]);
	render(InstitutionCombobox, {
		get choice() {
			return choice;
		},
		set choice(value) {
			choice = value;
		}
	});

	const input = page.getByLabelText('Institution');
	await input.fill('science');
	await expect.element(page.getByRole('option', { name: /University of Science/ })).toBeVisible();
	const inputElement = input.elements()[0] as HTMLInputElement;
	inputElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
	await input.fill('new query');
	inputElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

	expect(choice).toBeUndefined();
});

it('does not reopen search results when Escape is pressed during an in-flight search', async () => {
	let resolveSearch!: (institutions: typeof institution[]) => void;
	vi.mocked(searchInstitutions).mockImplementation(
		() => new Promise((resolve) => {
			resolveSearch = resolve;
		})
	);
	render(InstitutionCombobox);

	const input = page.getByLabelText('Institution');
	await input.fill('science');
	await expect.poll(() => vi.mocked(searchInstitutions).mock.calls).toHaveLength(1);
	const inputElement = input.elements()[0] as HTMLInputElement;
	inputElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
	resolveSearch([institution]);
	await new Promise((resolve) => setTimeout(resolve));

	await expect
		.element(page.getByRole('option', { name: /University of Science/ }))
		.not.toBeInTheDocument();
});

it('renders an account field error', async () => {
	render(InstitutionCombobox, { error: 'Choose an institution.' });

	await expect.element(page.getByText('Choose an institution.')).toBeVisible();
	await expect.element(page.getByLabelText('Institution')).toHaveAttribute('aria-invalid', 'true');
});
