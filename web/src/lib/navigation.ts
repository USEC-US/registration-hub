import type { Pathname } from '$app/types';
import { getLocale, locales, localizeHref } from '$lib/paraglide/runtime';

type Locale = (typeof locales)[number];
type CurrentUrl = Pick<URL, 'pathname' | 'search' | 'hash'>;

function hasUnsafeRedirectCharacter(value: string): boolean {
	for (const character of value) {
		const codePoint = character.codePointAt(0);
		if (
			codePoint !== undefined &&
			(codePoint === 0x5c || codePoint <= 0x1f || codePoint === 0x7f)
		) {
			return true;
		}
	}
	return false;
}

export function localizeInternalHref(href: string): Pathname {
	return localizeHref(href, { locale: getLocale() }) as Pathname;
}

export function localizeCurrentHref(currentUrl: CurrentUrl, locale: Locale): Pathname {
	return localizeHref(`${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`, {
		locale
	}) as Pathname;
}

export function sanitizeInternalRedirect(destination: string | null | undefined): Pathname {
	const fallback = () => localizeInternalHref('/account/registrations');
	if (!destination || !destination.startsWith('/') || destination.startsWith('//')) {
		return fallback();
	}
	if (hasUnsafeRedirectCharacter(destination)) return fallback();
	if (/%(?![0-9a-f]{2})/i.test(destination)) return fallback();

	try {
		const decodedDestination = decodeURIComponent(destination);
		if (decodedDestination.startsWith('//') || hasUnsafeRedirectCharacter(decodedDestination)) {
			return fallback();
		}
		if (new URL(destination, 'https://usec.internal').origin !== 'https://usec.internal') {
			return fallback();
		}
	} catch {
		return fallback();
	}

	return destination as Pathname;
}
