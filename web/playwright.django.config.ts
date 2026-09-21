import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

export default defineConfig({
	testDir: './e2e/django',
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 60_000,
	expect: { timeout: 10_000 },
	use: {
		baseURL: 'http://127.0.0.1:4175',
		locale: 'en-US',
		trace: 'retain-on-failure'
	},
	webServer: [
		{
			command: './.venv/bin/python e2e/serve.py',
			cwd: fileURLToPath(new URL('../server', import.meta.url)),
			url: 'http://127.0.0.1:8015/api/tournaments/',
			timeout: 120_000,
			reuseExistingServer: false,
			gracefulShutdown: { signal: 'SIGTERM', timeout: 15_000 }
		},
		{
			command: 'node ./node_modules/vite/bin/vite.js dev --host 127.0.0.1 --port 4175 --strictPort',
			url: 'http://127.0.0.1:4175/auth/sign-in',
			timeout: 120_000,
			env: {
				PUBLIC_API_BASE_URL: 'http://127.0.0.1:8015/api',
				PUBLIC_TURNSTILE_SITE_KEY: ''
			},
			reuseExistingServer: false,
			gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 }
		}
	]
});
