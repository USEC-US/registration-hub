import { expect, test } from '@playwright/test';

test('organizers correct and score matches from one responsive workspace', async ({ page }) => {
	await page.goto('http://127.0.0.1:8015/admin/competitions/competition/');
	await page.getByLabel('Email', { exact: false }).fill('journey-organizer@example.test');
	await page.getByLabel('Password', { exact: false }).fill('Journey-test-password-2026');
	await page.getByRole('button', { name: /Log in/ }).click();
	await page.getByRole('link', { name: 'Registration Journey Test · solo-free' }).click();
	const workspaceUrl = page.url();
	await expect(page.locator('a[href="/admin/competitions/match/"]')).toHaveCount(0);
	await expect(page.locator('a[href="/admin/competitions/matchslot/"]')).toHaveCount(0);

	await page
		.getByRole('article', { name: 'Bracket Player 2 vs Bracket Player 3' })
		.getByRole('link', { name: /Correct result/ })
		.click();
	const forfeitWinner = page.getByLabel('Winner (for a forfeit only)');
	await expect(forfeitWinner).toBeHidden();
	await page.getByLabel('How was the match decided?').selectOption('FORFEIT');
	await expect(forfeitWinner).toBeVisible();
	await page.getByLabel('How was the match decided?').selectOption('PLAYED');
	await expect(forfeitWinner).toBeHidden();
	await page.getByLabel('Bracket Player 2 — game wins').fill('2');
	await page.getByLabel('Bracket Player 3 — game wins').fill('0');
	await page.getByRole('button', { name: 'Preview correction' }).click();
	await expect(page.getByRole('heading', { name: 'These matches will be reset' })).toBeVisible();
	await page.getByLabel('Reason for correction').fill('Workspace browser test: replay the final.');
	await page.getByRole('button', { name: 'Confirm correction and resets' }).click();
	await page.getByRole('link', { name: /Bracket & matches/ }).click();
	const bracket = page.getByRole('region', { name: 'Competition bracket', exact: true });
	await bracket.focus();
	await expect(bracket).toBeFocused();

	await page.setViewportSize({ width: 390, height: 844 });
	await page.emulateMedia({ colorScheme: 'dark' });
	const layout = await page.evaluate(() => ({
		width: window.innerWidth,
		scrollWidth: document.documentElement.scrollWidth,
		overflow: Array.from(document.querySelectorAll('#main *'))
			.filter((element) => {
				const box = element.getBoundingClientRect();
				return box.right > window.innerWidth + 1 && box.left < window.innerWidth;
			})
			.map((element) => element.className)
	}));
	expect(layout.scrollWidth, JSON.stringify(layout.overflow)).toBe(layout.width);
	await page
		.getByRole('article', { name: 'Bracket Player 1 vs Bracket Player 2' })
		.getByRole('link', { name: /Enter result/ })
		.click();
	await page.getByLabel('Bracket Player 1 — game wins').fill('2');
	await page.getByLabel('Bracket Player 2 — game wins').fill('0');
	await page.getByRole('button', { name: 'Save result', exact: true }).click();
	await expect(page.getByLabel('Match score').getByText('Winner', { exact: true })).toBeVisible();
	await page.goto(`${workspaceUrl}?tab=changes`);
	await page
		.locator('.cw-change')
		.filter({ has: page.getByRole('link', { name: 'Result corrected', exact: true }) })
		.first()
		.getByText('View details', { exact: true })
		.click();
	await expect(page.getByText('Workspace browser test: replay the final.')).toBeVisible();
});
