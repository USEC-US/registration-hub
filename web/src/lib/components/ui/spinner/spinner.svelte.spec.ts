import { expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { Spinner } from './index';

it('renders a decorative spinner without requiring slotted content', () => {
	const { container } = render(Spinner, { 'aria-hidden': 'true' });

	expect(container.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
});
