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
