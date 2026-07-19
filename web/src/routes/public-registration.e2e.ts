import { expect, test } from '@playwright/test';

const tournament = {
	id: 1,
	name: 'USEC Summer 2026',
	slug: 'usec-summer-2026',
	description: 'Summer tournament',
	starts_at: '2026-08-15T01:00:00Z',
	ends_at: '2026-08-17T10:00:00Z',
	location: 'HCMUS',
	tournament_games: [
		{
			id: 9,
			game_name: 'Valorant',
			game_slug: 'valorant',
			team_size_min: 5,
			team_size_max: 5,
			registration_opens_at: '2026-07-20T01:00:00Z',
			registration_closes_at: '2026-08-10T10:00:00Z',
			registration_capacity: 32,
			capacity_remaining: 12,
			fee_amount: '50000.00',
			fee_currency: 'VND',
			registration_state: 'open',
			is_registration_open: true
		}
	]
};

test('browser navigation runs public universal loads without extra document requests', async ({
	page
}) => {
	const apiRequests: string[] = [];
	const documentRequests: string[] = [];

	page.on('request', (request) => {
		if (request.resourceType() === 'document') documentRequests.push(request.url());
	});

	await page.route('**/api/tournaments/', async (route) => {
		apiRequests.push(route.request().url());
		await route.fulfill({ json: [tournament] });
	});
	await page.route('**/api/tournaments/usec-summer-2026/', async (route) => {
		apiRequests.push(route.request().url());
		await route.fulfill({ json: tournament });
	});

	// Enter through a route with no API load so Playwright can observe the following
	// client-side universal loads. This smoke does not execute the public routes' SSR branch.
	await page.goto('/demo/playwright');
	await page.getByRole('link', { name: /USEC Tournament Registration Hub/ }).click();

	await expect(page).toHaveURL('/');
	await expect(
		page.getByRole('heading', { level: 1, name: 'USEC Tournament Registration Hub' })
	).toBeVisible();
	await expect(page.getByRole('heading', { name: tournament.name })).toBeVisible();
	await page.getByRole('link', { name: 'View tournament' }).click();

	await expect(page).toHaveURL('/tournaments/usec-summer-2026');
	await expect(page.getByRole('heading', { level: 1, name: tournament.name })).toBeVisible();
	await expect(page.getByRole('heading', { level: 2, name: 'Configured games' })).toBeVisible();
	await expect(page.getByRole('heading', { level: 3, name: 'Valorant' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Register' })).toBeVisible();

	expect(apiRequests).toEqual([
		'http://localhost:4173/api/tournaments/',
		'http://localhost:4173/api/tournaments/usec-summer-2026/'
	]);
	expect(documentRequests).toHaveLength(1);
});

test('profile redirects an unauthenticated visitor to sign in with the localized return path', async ({
	page
}) => {
	await page.goto('/account/profile?section=identity#school');

	await expect(page).toHaveURL(
		'/auth/sign-in?redirectTo=%2Faccount%2Fprofile%3Fsection%3Didentity%23school'
	);
	await expect(
		page.getByRole('heading', { level: 1, name: 'Sign in to your player account' })
	).toBeVisible();
});

test('client navigation to register redirects an unauthenticated visitor to sign in', async ({
	page
}) => {
	const documentRequests: string[] = [];
	page.on('request', (request) => {
		if (request.resourceType() === 'document') documentRequests.push(request.url());
	});

	await page.route('**/api/tournaments/', async (route) => {
		await route.fulfill({ json: [tournament] });
	});
	await page.route('**/api/tournaments/usec-summer-2026/', async (route) => {
		await route.fulfill({ json: tournament });
	});

	await page.goto('/demo/playwright');
	await page.getByRole('link', { name: /USEC Tournament Registration Hub/ }).click();
	await page.getByRole('link', { name: 'View tournament' }).click();
	await page.getByRole('link', { name: 'Register' }).click();

	await expect(page).toHaveURL(
		'/auth/sign-in?redirectTo=%2Ftournaments%2Fusec-summer-2026%2Fgames%2F9%2Fregister'
	);
	await expect(
		page.getByRole('heading', { level: 1, name: 'Sign in to your player account' })
	).toBeVisible();
	expect(documentRequests.map((requestUrl) => new URL(requestUrl).pathname)).toEqual([
		'/demo/playwright',
		'/auth/sign-in'
	]);
	expect(
		documentRequests.some((requestUrl) => new URL(requestUrl).pathname.endsWith('/register'))
	).toBe(false);
});
