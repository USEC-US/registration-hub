import { expect, test } from '@playwright/test';

test('spectators can navigate and read a corrected bracket in both locales', async ({ page }) => {
	await page.goto('/en/tournaments/registration-journey-test');
	const game = page.getByLabel('solo-free', { exact: true });
	await game.getByRole('link', { name: 'View bracket', exact: true }).click();

	await expect(page).toHaveURL(
		/\/en\/tournaments\/registration-journey-test\/games\/\d+\/bracket$/
	);
	await expect(
		page.getByRole('heading', { name: 'solo-free · Tournament bracket', exact: true })
	).toBeVisible();
	await expect(page.getByText('Bracket Player 1', { exact: true }).first()).toBeVisible();
	await expect(page.getByText(/result corrected$/).first()).toBeVisible();
	await expect(page.getByText('Browser-only correction fixture.')).toHaveCount(0);

	const rounds = page.locator('.desktop-bracket');
	await rounds.focus();
	await expect(rounds).toBeFocused();

	const bracketPath = new URL(page.url()).pathname.replace(/^\/en\//, '/vi/');
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto(bracketPath);
	await expect(
		page.getByRole('heading', { name: 'solo-free · Nhánh đấu', exact: true })
	).toBeVisible();
	await expect(page.getByText(/Đã sửa kết quả trận/).first()).toBeVisible();
	await expect(page.locator('.mobile-bracket')).toBeVisible();
	await expect(page.locator('.desktop-bracket')).toBeHidden();
	expect(
		await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
	).toBeTruthy();
});

test('double brackets expose upper, lower and finals sections in EN and VI on mobile', async ({
	page
}) => {
	await page.goto('/en/tournaments/double-elimination-journey-test');
	await page
		.getByLabel('double-public', { exact: true })
		.getByRole('link', { name: 'View bracket', exact: true })
		.click();
	for (const name of ['Upper bracket', 'Lower bracket', 'Finals']) {
		await expect(page.getByRole('heading', { name, exact: true, level: 3 })).toBeVisible();
	}
	const brackets = page.locator('.desktop-bracket');
	await brackets.first().focus();
	await expect(brackets.first()).toBeFocused();
	await page.keyboard.press('Tab');
	await expect(brackets.nth(1)).toBeFocused();
	await expect(
		page.getByText('The first final decides the champion; no reset final is played.')
	).toBeVisible();
	const path = new URL(page.url()).pathname;
	await page.setViewportSize({ width: 390, height: 844 });
	for (const locale of ['en', 'vi']) {
		await page.goto(path.replace(/^\/en\//, `/${locale}/`));
		const names =
			locale === 'en'
				? ['Upper bracket', 'Lower bracket', 'Finals']
				: ['Nhánh thắng', 'Nhánh thua', 'Chung kết'];
		for (const name of names)
			await expect(page.getByRole('heading', { name, exact: true, level: 3 })).toBeVisible();
		await expect(page.locator('.mobile-bracket').first()).toBeVisible();
		expect(
			await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
		).toBeTruthy();
	}
});

test('round robin groups show unequal standings, rests, qualification and history in EN and VI', async ({
	page
}) => {
	const tournament = await (
		await page.request.get('http://127.0.0.1:8015/api/tournaments/round-robin-journey-test/')
	).json();
	const division = tournament.tournament_games.find(
		(game: { game_slug: string }) => game.game_slug === 'rr-fixed'
	);
	for (const locale of ['en', 'vi']) {
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto(`/${locale}/tournaments/round-robin-journey-test/games/${division.id}/bracket`);
		await expect(page.getByRole('table').locator('tbody tr')).toHaveCount(3);
		await expect(
			page.getByText(locale === 'en' ? 'Historical' : 'Lịch sử', { exact: true }).first()
		).toBeVisible();
		await expect(
			page
				.getByText(locale === 'en' ? 'Organizer decision' : 'Quyết định của ban tổ chức', {
					exact: true
				})
				.first()
		).toBeVisible();
		const group = page.getByLabel(locale === 'en' ? 'Group' : 'Bảng', { exact: true });
		await expect(group).toBeEnabled();
		await group.focus();
		await expect(group).toBeFocused();
		await page.keyboard.press('Space');
		await page.keyboard.press('End');
		await page.keyboard.press('Enter');
		await expect(page.getByRole('table').locator('tbody tr')).toHaveCount(5);
		const standings = page.getByRole('region', {
			name: locale === 'en' ? 'Standings' : 'Bảng xếp hạng',
			exact: true
		});
		await standings.focus();
		await page.keyboard.press('ArrowRight');
		await expect.poll(() => standings.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
		expect(
			await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
		).toBeTruthy();
		await expect(
			page
				.getByText(
					locale === 'en' ? 'Awaiting qualification resolution' : 'Chờ phân định suất đi tiếp',
					{ exact: true }
				)
				.first()
		).toBeVisible();
		await page
			.getByRole('link', {
				name: locale === 'en' ? 'Refresh bracket' : 'Làm mới nhánh đấu',
				exact: true
			})
			.focus();
	}
});
