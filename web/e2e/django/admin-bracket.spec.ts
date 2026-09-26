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
	await expect(
		page.getByRole('heading', { name: 'These match results will be cleared' })
	).toBeVisible();
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

test('organizers publish a double bracket, play a reset, and correct its activation', async ({
	page,
	context
}) => {
	test.setTimeout(120_000);
	page.setDefaultTimeout(10_000);
	const response = await page.request.get(
		'http://127.0.0.1:8015/api/tournaments/double-elimination-journey-test/'
	);
	const tournament = await response.json();
	const division = tournament.tournament_games.find(
		(game: { game_slug: string }) => game.game_slug === 'double-reset'
	);
	const publicPath = `/en/tournaments/double-elimination-journey-test/games/${division.id}/bracket`;
	const apiUrl = `http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`;
	await page.goto(`http://127.0.0.1:8015/admin/competitions/competition/create/${division.id}/`);
	await page.getByLabel('Email', { exact: false }).fill('journey-organizer@example.test');
	await page.getByLabel('Password', { exact: false }).fill('Journey-test-password-2026');
	await page.getByRole('button', { name: /Log in/ }).click();
	await page.getByRole('button', { name: 'Continue to setup', exact: true }).click();
	const workspaceUrl = page.url();
	await page.getByRole('link', { name: /Continue\s*:\s*Set up/ }).click();
	await page.getByLabel('Format:').selectOption('DOUBLE_ELIMINATION');
	await page.getByLabel('Grand final policy').selectOption('RESET');
	await page.getByLabel('Stage name').fill('Browser reset bracket');
	await page.getByLabel('Games per match (best of)').fill('1');
	await page.getByRole('button', { name: 'Save setup' }).click();
	await page.getByRole('link', { name: /Continue\s*:\s*Choose entrants/ }).click();
	for (let index = 1; index <= 4; index++)
		await page.getByLabel(`DE Team ${index}`, { exact: true }).check();
	await page.getByRole('button', { name: 'Save entrants' }).click();
	await page.getByRole('link', { name: /Continue\s*:\s*Seed the bracket/ }).click();
	await expect(page.getByLabel('Seed 1:')).toBeVisible();
	await page.getByRole('button', { name: 'Save and preview bracket' }).click();
	await expect(page.getByText('Private preview', { exact: true })).toBeVisible();
	expect((await page.request.get(apiUrl)).status()).toBe(404);
	for (const name of ['Upper bracket', 'Lower bracket', 'Grand final']) {
		await expect(page.getByRole('heading', { name: new RegExp(name) }).first()).toBeVisible();
	}
	await page.goto(`${workspaceUrl}?tab=setup`);
	await page.getByRole('link', { name: /Continue\s*:\s*Publish/ }).click();
	await expect(page.getByText(/Grand final policy: Reset/)).toBeVisible();
	await page.getByRole('button', { name: 'Publish bracket' }).click();
	const spectator = await context.newPage();
	await spectator.goto(publicPath);
	await expect(spectator.getByText('If needed', { exact: true }).first()).toBeVisible();

	async function score(code: string, sideOne: number, sideTwo: number) {
		await page.goto(`${workspaceUrl}?tab=bracket`);
		await page.getByRole('link', { name: new RegExp(`Enter result for .*${code}$`) }).click();
		await page.locator('input[name="side_one_score"]').fill(String(sideOne));
		await page.locator('input[name="side_two_score"]').fill(String(sideTwo));
		await page.getByRole('button', { name: 'Save result', exact: true }).click();
	}
	for (const code of ['UPPER-R1-M1', 'UPPER-R1-M2', 'UPPER-R2-M1', 'LOWER-R1-M1', 'LOWER-R2-M1'])
		await score(code, 1, 0);
	await score('FINALS-R1-M1', 0, 1);
	await spectator.reload();
	await expect(spectator.getByText('If needed', { exact: true })).toHaveCount(0);
	await score('FINALS-R2-M1', 1, 0);
	await spectator.reload();
	await expect(spectator.getByRole('heading', { name: 'Champion', exact: true })).toBeVisible();
	await page.goto(`${workspaceUrl}?tab=bracket`);
	await page.getByRole('link', { name: /Correct result for .*FINALS-R1-M1$/ }).click();
	await page.locator('input[name="side_one_score"]').fill('1');
	await page.locator('input[name="side_two_score"]').fill('0');
	await page.getByRole('button', { name: 'Preview correction' }).click();
	await expect(
		page.getByRole('heading', { name: 'These match results will be cleared' })
	).toBeVisible();
	await expect(
		page.getByRole('heading', { name: 'Reserved final activation changes' })
	).toBeVisible();
	await expect(page.getByText(/Active.*Not required/)).toBeVisible();
	await page.getByLabel('Reason for correction').fill('Private DE browser correction reason');
	await page.getByRole('button', { name: 'Confirm correction and resets' }).click();
	await spectator.reload();
	await expect(spectator.getByText('Not required', { exact: true }).first()).toBeVisible();
	await expect(spectator.getByText(/Active → Not required/)).toBeVisible();
	await expect(spectator.getByText('Private DE browser correction reason')).toHaveCount(0);
	const publicData = await (await page.request.get(apiUrl)).text();
	expect(publicData).not.toContain('Private DE browser correction reason');
	expect(publicData).not.toContain('@example.invalid');
	const changes = await (await page.request.get(`${apiUrl}changes/`)).json();
	const correction = changes.results.find(
		(change: { kind: string }) => change.kind === 'result_corrected'
	);
	expect(correction.reset_matches).toEqual([
		expect.objectContaining({ side_one_score: 1, side_two_score: 0 })
	]);
	expect(correction.reset_final_changes).toEqual([
		expect.objectContaining({ before: 'ACTIVE', after: 'NOT_REQUIRED' })
	]);
	expect(JSON.stringify(changes)).not.toContain('Private DE browser correction reason');
	await spectator.close();
});
