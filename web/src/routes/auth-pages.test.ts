import { expect, it } from 'vitest';
import { ssr } from './account/profile/+page';

it('keeps the localStorage-authenticated profile page client-only', () => {
	expect(ssr).toBe(false);
});
