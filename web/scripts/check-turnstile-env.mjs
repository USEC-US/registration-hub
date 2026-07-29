import { loadEnv } from 'vite';

const siteKey = loadEnv('production', process.cwd(), 'PUBLIC_').PUBLIC_TURNSTILE_SITE_KEY?.trim();

if (!siteKey) {
	console.error('PUBLIC_TURNSTILE_SITE_KEY is required for production builds.');
	process.exit(1);
}
