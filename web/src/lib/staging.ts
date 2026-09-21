export function isStagingHost(
	url: { hostname: string; searchParams?: URLSearchParams },
	isDev: boolean = false
): boolean {
	if (url.hostname.includes('staging')) {
		return true;
	}

	if (isDev && url.searchParams?.has('staging')) {
		return true;
	}

	return false;
}
