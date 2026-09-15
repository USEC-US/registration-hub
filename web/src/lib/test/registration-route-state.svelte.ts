import { SvelteURL } from 'svelte/reactivity';
/** Reactive SvelteKit page substitute for same-component route navigation tests. */
export const registrationRoutePage = $state<{ url: URL; params: { id: string } }>({
	url: new SvelteURL('https://usec.test/registrations/33/payment'),
	params: { id: '33' }
});
