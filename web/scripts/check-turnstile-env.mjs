const siteKey = process.env.PUBLIC_TURNSTILE_SITE_KEY?.trim();

if (!siteKey) {
	console.error('PUBLIC_TURNSTILE_SITE_KEY is required for production builds.');
	process.exit(1);
}
