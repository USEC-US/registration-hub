import { browser } from '$app/environment';

export function replaceInternalLocation(href: string): void {
	if (!browser) return;
	window.location.replace(href);
}
