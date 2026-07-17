import type { Pathname } from '$app/types';
import { resolve } from '$app/paths';
import type { Locale as _Locale } from '$lib/paraglide/runtime';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { page } from '$app/state';

import {
	baseLocale,
	localizeHref,
	overwriteGetLocale,
	overwriteSetLocale,
	toLocale
} from '$lib/paraglide/runtime';

export class Locale {
	#current: _Locale = $state(
		toLocale(browser && document.querySelector('html')?.lang) ?? baseLocale
	);

	constructor() {
		overwriteGetLocale(() => this.#current);

		overwriteSetLocale((locale) => {
			this.#current = locale;
			goto(resolve(localizeHref(page.url.pathname, { locale }) as Pathname));
		});
	}
}
