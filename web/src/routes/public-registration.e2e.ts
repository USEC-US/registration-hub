import { expect, test } from '@playwright/test';

const tournament = {
	id: 1,
	name: 'USEC Summer 2026',
	slug: 'usec-summer-2026',
	description: 'Summer tournament',
	cover_image: null,
	starts_at: '2026-08-15T01:00:00Z',
	ends_at: '2026-08-17T10:00:00Z',
	location: 'HCMUS',
	is_featured: false,
	students_only: false,
	tournament_games: [
		{
			id: 9,
			game_name: 'Valorant',
			game_slug: 'valorant',
			main_roster_size: 5,
			substitute_limit: 0,
			registration_opens_at: '2026-07-20T01:00:00Z',
			registration_closes_at: '2026-08-10T10:00:00Z',
			registration_capacity: 32,
			capacity_remaining: 12,
			fee_amount: '50000.00',
			fee_currency: 'VND',
			registration_state: 'open',
			is_registration_open: true,
			payment_hold_minutes: 60,
			payment_available: true
		}
	]
};

test('browser navigation runs public universal loads without extra document requests', async ({
	page
}) => {
	const apiRequests: string[] = [];
	const documentRequests: string[] = [];

	page.on('request', (request) => {
		if (request.resourceType() === 'document' && request.frame() === page.mainFrame()) {
			documentRequests.push(request.url());
		}
	});

	await page.route('**/api/tournaments/', async (route) => {
		apiRequests.push(route.request().url());
		await route.fulfill({ json: [tournament] });
	});
	await page.route('**/api/tournaments/usec-summer-2026/', async (route) => {
		apiRequests.push(route.request().url());
		await route.fulfill({ json: tournament });
	});

	// Enter through a real route with no API load so Playwright can observe the following
	// client-side universal loads. This smoke does not execute the public routes' SSR branch.
	await page.goto('/auth/sign-in');
	await page.locator('a[href="/"]').first().click();

	await expect(page).toHaveURL('/');
	await expect(
		page.getByRole('heading', { level: 1, name: 'Hết mình thi đấu. Hết lòng kết nối.' })
	).toBeVisible();
	await expect(page.getByRole('heading', { name: tournament.name })).toBeVisible();
	await page.getByRole('link', { name: tournament.name }).first().click();

	await expect(page).toHaveURL('/tournaments/usec-summer-2026');
	await expect(page.getByRole('heading', { level: 3, name: tournament.name })).toBeVisible();
	await expect(page.getByRole('heading', { level: 3, name: 'Valorant' })).toBeVisible();
	await expect(
		page.locator('a[href="/tournaments/usec-summer-2026/games/9/register"]')
	).toBeVisible();

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
		'/auth/sign-in?redirect=%2Faccount%2Fprofile%3Fsection%3Didentity%23school'
	);
	await expect(page.getByRole('heading', { level: 1, name: 'Đăng nhập tài khoản' })).toBeVisible();
});

test('client navigation keeps a guest on the shared registration form', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 844 });
	const documentRequests: string[] = [];
	page.on('request', (request) => {
		if (request.resourceType() === 'document' && request.frame() === page.mainFrame())
			documentRequests.push(request.url());
	});

	await page.route('**/api/tournaments/', async (route) => {
		await route.fulfill({ json: [tournament] });
	});
	await page.route('**/api/tournaments/usec-summer-2026/', async (route) => {
		await route.fulfill({ json: tournament });
	});

	await page.goto('/auth/sign-in');
	await page.locator('a[href="/"]').first().click();
	await page.getByRole('link', { name: tournament.name }).first().click();
	await page.locator('a[href="/tournaments/usec-summer-2026/games/9/register"]').click();

	await expect(page).toHaveURL('/tournaments/usec-summer-2026/games/9/register');
	await expect(page.locator('button[type="submit"]')).toBeVisible();
	await expect(page.locator('input[name="contact_facebook_snapshot"]')).toBeVisible();
	await expect(page.locator('input[name="member-1-gamer-tag"]')).toHaveCount(0);
	await page.locator('input[name="team_name"]').fill('Blue Team');
	await page.locator('input[name="team_tag"]').fill('BLUE');
	await page.locator('input[name="contact_facebook_snapshot"]').fill('facebook.com/player');
	await page.locator('input[name="contact_phone_snapshot"]').fill('0901234567');
	await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
	await expect(page).toHaveURL(/step=roster/);
	await page.locator('input[name="member-1-gamer-tag"]').fill('Saved captain');
	await page.goBack();
	await expect(page.locator('input[name="team_name"]')).toHaveValue('Blue Team');
	await page.goForward();
	await expect(page.locator('input[name="member-1-gamer-tag"]')).toHaveValue('Saved captain');
	await page.goBack();
	await expect(page.locator('input[name="team_name"]')).toHaveValue('Blue Team');
	await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
	await expect(page.locator('input[name="member-1-gamer-tag"]')).toHaveValue('Saved captain');
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
		true
	);
	expect(documentRequests.map((requestUrl) => new URL(requestUrl).pathname)).toEqual([
		'/auth/sign-in'
	]);
});
