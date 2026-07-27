import { expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Field from './Field.svelte';

it('forwards validation limits and describes both hint and error text', async () => {
	render(Field, {
		label: 'Gamer tag',
		name: 'gamer_tag',
		value: '',
		hint: 'Use the name shown in tournament play.',
		error: 'Enter a gamer tag.',
		required: true,
		minlength: 2,
		maxlength: 64
	});

	const input = page.getByRole('textbox', { name: 'Gamer tag' });
	await expect.element(input).toHaveAttribute('required', '');
	await expect.element(input).toHaveAttribute('minlength', '2');
	await expect.element(input).toHaveAttribute('maxlength', '64');
	await expect.element(input).toHaveAttribute('aria-describedby', 'gamer_tag-hint gamer_tag-error');
	await expect
		.element(page.getByText('Use the name shown in tournament play.'))
		.toHaveAttribute('id', 'gamer_tag-hint');
});

it('exposes the generated field and input semantics when invalid', async () => {
	render(Field, {
		label: 'Gamer tag',
		name: 'gamer_tag',
		value: '',
		error: 'Enter a gamer tag.'
	});

	await expect.element(page.getByRole('group')).toHaveAttribute('data-invalid', 'true');
	await expect
		.element(page.getByRole('textbox', { name: 'Gamer tag' }))
		.toHaveAttribute('data-slot', 'input');
	await expect.element(page.getByText('Enter a gamer tag.')).toHaveAttribute('data-slot', 'field-error');
});
