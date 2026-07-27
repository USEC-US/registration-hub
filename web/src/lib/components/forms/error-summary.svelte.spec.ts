import { expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import ErrorSummary from './ErrorSummary.svelte';

it('renders every error within the generated destructive alert structure', async () => {
	const { container } = render(ErrorSummary, { errors: ['First problem.', 'Second problem.'] });

	await expect.element(page.getByRole('alert')).toHaveAttribute('data-slot', 'alert');
	await expect.element(page.getByRole('heading')).toHaveAttribute('data-slot', 'alert-title');
	await expect.element(page.getByText('First problem.')).toBeInTheDocument();
	await expect.element(page.getByText('Second problem.')).toBeInTheDocument();
	expect(container.querySelectorAll('li')).toHaveLength(2);
});
