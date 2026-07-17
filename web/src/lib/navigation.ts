import type { Pathname } from '$app/types';
import { getLocale, locales, localizeHref } from '$lib/paraglide/runtime';

type Locale = (typeof locales)[number];
type CurrentUrl = Pick<URL, 'pathname' | 'search' | 'hash'>;

export function localizeInternalHref(href: string): Pathname {
	return localizeHref(href, { locale: getLocale() }) as Pathname;
}

export function localizeCurrentHref(currentUrl: CurrentUrl, locale: Locale): Pathname {
	return localizeHref(`${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`, {
		locale
	}) as Pathname;
}
