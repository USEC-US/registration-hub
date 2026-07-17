import { defineConfig } from '@playwright/test';

export default defineConfig({
	use: { baseURL: 'http://localhost:4173' },
	webServer: {
		command: 'npm run build && npm run preview',
		env: { PUBLIC_API_BASE_URL: 'http://localhost:4173/api' },
		port: 4173
	},
	testMatch: '**/*.e2e.{ts,js}'
});
