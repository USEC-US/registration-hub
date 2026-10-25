import { expect, test } from '@playwright/test';
import type { PublicCompetition, PublicCompetitionChange } from '../../src/lib/api/types';

test('double brackets place the lower bracket below the upper bracket and finals on the right', async ({
	page
}) => {
	page.setDefaultTimeout(10_000);
	await page.goto('http://127.0.0.1:8015/admin/competitions/competition/');
	await page.getByLabel('Email', { exact: false }).fill('journey-organizer@example.test');
	await page.getByLabel('Password', { exact: false }).fill('Journey-test-password-2026');
	await page.getByRole('button', { name: /Log in/ }).click();
	const tournament = await (
		await page.request.get('http://127.0.0.1:8015/api/tournaments/double-elimination-journey-test/')
	).json();
	for (const scenario of [
		{ slug: 'double-public', matches: 6, lowerRounds: 2, finals: 1 },
		{ slug: 'double-large', matches: 31, lowerRounds: 6, finals: 2 },
		{ slug: 'double-two', matches: 2, lowerRounds: 0, finals: 1 }
	]) {
		await page.setViewportSize({ width: 1440, height: 1000 });
		await page.goto('http://127.0.0.1:8015/admin/competitions/competition/');
		await page
			.getByRole('link', { name: `Double Elimination Journey Test · ${scenario.slug}` })
			.click();
		const bracket = page.getByRole('region', { name: 'Competition bracket', exact: true });
		const division = tournament.tournament_games.find(
			(game: { game_slug: string }) => game.game_slug === scenario.slug
		);
		const competition: PublicCompetition = await (
			await page.request.get(
				`http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`
			)
		).json();
		const routes = competition.stages[0].rounds.flatMap((round) =>
			round.matches.flatMap((match) =>
				match.slots
					.filter((slot) => slot.source_match_id)
					.map((slot) => ({
						match: String(match.id),
						source: String(slot.source_match_id),
						position: String(slot.position),
						outcome: slot.source_outcome
					}))
			)
		);
		await expect(bracket.locator('.cw-bracket-lines path')).toHaveCount(routes.length);
		expect(
			await bracket.locator('.cw-bracket-lines path').evaluateAll((paths) =>
				paths.map((path) => ({
					match: path.getAttribute('data-match'),
					source: path.getAttribute('data-source'),
					position: path.getAttribute('data-position'),
					outcome: path.getAttribute('data-outcome')
				}))
			)
		).toEqual(expect.arrayContaining(routes));
		await expect(bracket.locator('.cw-match')).toHaveCount(scenario.matches);
		await expect(bracket.locator('[data-section="LOWER"] .cw-round')).toHaveCount(
			scenario.lowerRounds
		);
		await expect(bracket.locator('[data-section="FINALS"] .cw-round')).toHaveCount(scenario.finals);
		for (const viewport of [
			{ width: 1440, height: 1000 },
			{ width: 390, height: 844 }
		]) {
			await page.setViewportSize(viewport);
			const upper = await bracket.locator('[data-section="UPPER"]').boundingBox();
			const finals = await bracket.locator('[data-section="FINALS"]').boundingBox();
			expect(upper).not.toBeNull();
			expect(finals).not.toBeNull();
			let bracketRight = upper!.x + upper!.width;
			if (scenario.lowerRounds) {
				const lower = await bracket.locator('[data-section="LOWER"]').boundingBox();
				expect(lower).not.toBeNull();
				expect(lower!.y).toBeGreaterThanOrEqual(upper!.y + upper!.height);
				expect(lower!.x).toBe(upper!.x);
				bracketRight = Math.max(bracketRight, lower!.x + lower!.width);
			}
			expect(finals!.x).toBeGreaterThanOrEqual(bracketRight);
			for (const scrollLeft of [0, 5000]) {
				await bracket.evaluate((element, left) => {
					element.scrollLeft = left;
				}, scrollLeft);
				await expect
					.poll(() =>
						bracket.locator('.cw-bracket-lines path').evaluateAll((elements) => {
							const errors: string[] = [];
							for (const element of elements) {
								const path = element as SVGPathElement;
								const root = path.closest('.cw-bracket')!;
								const source = root.querySelector(`[data-match-id="${path.dataset.source}"]`)!;
								const target = root.querySelector(
									`[data-match-id="${path.dataset.match}"] [data-position="${path.dataset.position}"]`
								)!;
								const sourceBox = source.getBoundingClientRect();
								const targetBox = target.getBoundingClientRect();
								const transform = path.getScreenCTM()!;
								const length = path.getTotalLength();
								const start = path.getPointAtLength(0).matrixTransform(transform);
								const end = path.getPointAtLength(length).matrixTransform(transform);
								if (
									Math.abs(start.x - sourceBox.right) > 1 ||
									start.y <= sourceBox.top ||
									start.y >= sourceBox.bottom ||
									Math.abs(end.x - targetBox.left) > 1 ||
									Math.abs(end.y - (targetBox.top + targetBox.height / 2)) > 1
								) {
									errors.push(`Misaligned route: ${path.dataset.source} to ${path.dataset.match}`);
								}
								const obstacles = Array.from(
									root.querySelectorAll('.cw-match, .cw-round-heading')
								).map((card) => card.getBoundingClientRect());
								for (let distance = 2; distance < length; distance += 4) {
									const point = path.getPointAtLength(distance).matrixTransform(transform);
									if (
										obstacles.some(
											(box) =>
												point.x > box.left + 1 &&
												point.x < box.right - 1 &&
												point.y > box.top + 1 &&
												point.y < box.bottom - 1
										)
									) {
										errors.push(
											`Route crosses a card or heading: ${path.dataset.source} to ${path.dataset.match}`
										);
										break;
									}
								}
							}
							return errors;
						})
					)
					.toEqual([]);
			}
			await bracket.focus();
			await expect(bracket).toBeFocused();
			expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
			if (viewport.width === 1440) {
				await bracket.evaluate((element) => {
					element.scrollLeft = 0;
				});
				await test.info().attach(scenario.slug, {
					body: await page.screenshot({
						path: `/tmp/${scenario.slug}-connectors.png`,
						fullPage: true
					}),
					contentType: 'image/png'
				});
			}
		}
	}
});

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
	await page.getByLabel('Games per match:', { exact: true }).fill('1');
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
	const published: PublicCompetition = await (await page.request.get(apiUrl)).json();
	const finals = published.stages[0].rounds.filter((round) => round.section === 'FINALS');
	for (const match of published.stages[0].rounds
		.filter((round) => round.section !== 'FINALS')
		.flatMap((round) => round.matches))
		await score(match.code, 1, 0);
	await score(finals[0].matches[0].code, 0, 1);
	await spectator.reload();
	await expect(spectator.getByText('If needed', { exact: true })).toHaveCount(0);
	await score(finals[1].matches[0].code, 1, 0);
	const completedBracket: PublicCompetition = await (await page.request.get(apiUrl)).json();
	const completedReset = completedBracket.stages[0].rounds
		.flatMap((round) => round.matches)
		.find((match) => match.id === finals[1].matches[0].id)!;
	await spectator.reload();
	await expect(spectator.getByRole('heading', { name: 'Champion', exact: true })).toBeVisible();
	await page.goto(`${workspaceUrl}?tab=bracket`);
	await page
		.getByRole('link', { name: new RegExp(`Correct result for .*${finals[0].matches[0].code}$`) })
		.click();
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
	await expect(
		spectator.getByText(
			`${completedReset.code}: Played · ${completedReset.slots[0].entry!.display_name} 1–0 ${completedReset.slots[1].entry!.display_name} · ${completedReset.winner!.display_name} won`,
			{ exact: true }
		)
	).toBeVisible();
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

test('organizers publish groups, resolve ties and correct results while spectators retain history', async ({
	page,
	context
}) => {
	test.setTimeout(120_000);
	const tournament = await (
		await page.request.get('http://127.0.0.1:8015/api/tournaments/round-robin-journey-test/')
	).json();
	const division = tournament.tournament_games.find(
		(game: { game_slug: string }) => game.game_slug === 'rr-workflow'
	);
	const apiUrl = `http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`;
	await page.goto(`http://127.0.0.1:8015/admin/competitions/competition/create/${division.id}/`);
	await page.getByLabel('Email', { exact: false }).fill('journey-organizer@example.test');
	await page.getByLabel('Password', { exact: false }).fill('Journey-test-password-2026');
	await page.getByRole('button', { name: /Log in/ }).click();
	await page.getByRole('button', { name: 'Continue to setup', exact: true }).click();
	const workspace = page.url();
	await page.getByRole('link', { name: /Continue\s*:\s*Set up/ }).click();
	await page.getByLabel('Format:', { exact: true }).selectOption('ROUND_ROBIN');
	await page.getByLabel('Group sizes', { exact: false }).selectOption('EXACT');
	await page.getByLabel('Stage name').fill('Browser groups');
	await page.getByLabel('Group 1 name').fill('Alpha');
	await page.getByLabel('Group 1 entrants').selectOption('3');
	await page.getByLabel('Series mode').selectOption('FIXED_GAMES');
	await page.getByLabel('Games per match:', { exact: true }).fill('2');
	for (let i = 1; i <= 4; i++)
		await page.getByLabel(`Tiebreaker ${i}:`, { exact: true }).selectOption('');
	await page.getByRole('button', { name: 'Save setup', exact: true }).click();
	await page.getByRole('link', { name: /Continue\s*:\s*Choose entrants/ }).click();
	for (let i = 1; i <= 3; i++) await page.getByLabel(`RR Team ${i}`, { exact: true }).check();
	await page.getByRole('button', { name: 'Save entrants', exact: true }).click();
	await page.getByRole('link', { name: /Continue\s*:\s*Seed the bracket/ }).click();
	await page.getByRole('button', { name: 'Save and preview bracket', exact: true }).click();
	await expect(page.getByText('Private preview', { exact: true })).toBeVisible();
	expect((await page.request.get(apiUrl)).status()).toBe(404);
	await page.goto(`${workspace}?tab=setup`);
	await page.getByRole('link', { name: /Continue\s*:\s*Publish/ }).click();
	await page.getByRole('button', { name: 'Publish bracket', exact: true }).click();
	const snapshot = async (): Promise<PublicCompetition> => (await page.request.get(apiUrl)).json();
	const ordinary = (await snapshot()).stages[0].rounds.flatMap((r) => r.matches);
	async function score(id: number, first: number, second: number, correction = false) {
		await page.goto(`http://127.0.0.1:8015/admin/competitions/match/${id}/change/`);
		await page
			.getByRole('link', { name: correction ? 'Correct result' : 'Enter result', exact: true })
			.click();
		await page.locator('[name="side_one_score"]').fill(String(first));
		await page.locator('[name="side_two_score"]').fill(String(second));
		await page
			.getByRole('button', { name: correction ? 'Preview correction' : 'Save result', exact: true })
			.click();
		if (correction) {
			await expect(page.getByRole('heading', { name: 'Alpha qualification impact' })).toBeVisible();
			await page.getByLabel('Reason for correction').fill('PRIVATE-RR-BROWSER');
			await page
				.getByRole('button', { name: 'Confirm correction and resets', exact: true })
				.click();
		}
	}
	for (const match of ordinary) await score(match.id, 1, 1);
	const spectator = await context.newPage();
	await spectator.goto(`/en/tournaments/round-robin-journey-test/games/${division.id}/bracket`);
	await expect(
		spectator.getByText('Awaiting qualification resolution', { exact: true })
	).toBeVisible();
	async function choose(method: 'MANUAL' | 'EXTRA_MATCHES') {
		await page.goto(`${workspace}?tab=standings`);
		await page.getByRole('link', { name: 'Resolve qualification tie', exact: true }).click();
		await page.getByLabel('Resolve qualification tie').selectOption(method);
		if (method === 'EXTRA_MATCHES') await page.getByLabel('Extra contests: best of').fill('1');
		await page.getByRole('button', { name: 'Preview tie choice', exact: true }).click();
		await expect(
			page.getByRole('heading', { name: 'Review qualification tie', exact: true })
		).toBeVisible();
		await page.getByLabel('Private organizer reason').fill('PRIVATE-RR-TIE');
		await page.getByRole('button', { name: 'Confirm qualification tie', exact: true }).click();
	}
	await choose('MANUAL');
	await spectator.reload();
	await expect(spectator.getByText('Organizer decision', { exact: true })).toBeVisible();
	await score(ordinary[0].id, 2, 0, true);
	await score(ordinary[0].id, 1, 1, true);
	await choose('EXTRA_MATCHES');
	const extras = (await snapshot()).stages[0].rounds
		.filter((r) => r.section === 'TIEBREAK')
		.flatMap((r) => r.matches);
	for (const match of extras) {
		const firstWins = match.slots[0].entry!.seed < match.slots[1].entry!.seed;
		await score(match.id, Number(firstWins), Number(!firstWins));
	}
	await spectator.reload();
	await expect(spectator.getByText('Group stage complete', { exact: true })).toBeVisible();
	await score(ordinary[0].id, 2, 0, true);
	await spectator.reload();
	const historicalRound = (await snapshot()).stages[0].rounds.find((round) =>
		round.matches.some((match) => match.historical)
	)!;
	await spectator.getByLabel('Round', { exact: true }).selectOption(String(historicalRound.id));
	await expect(spectator.getByText('Historical', { exact: true }).first()).toBeVisible();
	const final = await snapshot();
	expect(
		final.stages[0].rounds
			.filter((r) => r.section === 'TIEBREAK')
			.every((r) => r.matches.every((m) => m.historical && m.status === 'FINAL'))
	).toBeTruthy();
	expect(JSON.stringify(final)).not.toContain('PRIVATE-RR');
	expect(await spectator.locator('body').textContent()).not.toContain('PRIVATE-RR');
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto(`${workspace}?tab=standings`);
	const table = page.getByRole('region', { name: 'Group standings' });
	await table.focus();
	await expect(table).toBeFocused();
	expect(
		await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
	).toBeTruthy();
	await spectator.close();
});

test('multi-stage organizers lock groups, publish a saved draw and retire played playoffs', async ({
	page,
	context
}) => {
	test.setTimeout(180_000);
	const tournament = await (
		await page.request.get('http://127.0.0.1:8015/api/tournaments/multi-stage-journey-test/')
	).json();
	const division = tournament.tournament_games.find(
		(game: { game_slug: string }) => game.game_slug === 'ms-workflow'
	);
	const apiUrl = `http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`;
	await page.goto(`http://127.0.0.1:8015/admin/competitions/competition/create/${division.id}/`);
	await page.getByLabel('Email', { exact: false }).fill('journey-organizer@example.test');
	await page.getByLabel('Password', { exact: false }).fill('Journey-test-password-2026');
	await page.getByRole('button', { name: /Log in/ }).click();
	await page.getByRole('button', { name: 'Continue to setup', exact: true }).click();
	const workspace = page.url().split('?')[0];
	await page.getByRole('link', { name: /Continue\s*:\s*Set up/ }).click();
	await page.getByLabel('Format:', { exact: true }).selectOption('ROUND_ROBIN');
	await page.getByLabel('Group sizes', { exact: false }).selectOption('EXACT');
	await page.getByLabel('Stage name').fill('Groups1');
	await page.getByLabel('Number of groups').selectOption('3');
	for (const [index, name, size] of [
		[1, 'Alpha', '3'],
		[2, 'Beta', '3'],
		[3, 'Gamma', '2']
	] as const) {
		await page.getByLabel(`Group ${index} name`).fill(name);
		await page.getByLabel(`Group ${index} entrants`).selectOption(size);
		await page.getByLabel(`Group ${index} qualifiers`).selectOption('2');
	}
	await expect(page.locator('[data-group-summary]')).toHaveText('8 entrants · 6 qualify');
	await expect(page.getByLabel('Group 3 qualifiers').locator('option[value="3"]')).toBeDisabled();
	await page.setViewportSize({ width: 390, height: 844 });
	expect(
		await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
	).toBeTruthy();
	await page.getByLabel('Series mode').selectOption('FIXED_GAMES');
	await page.getByLabel('Games per match:', { exact: true }).fill('2');
	for (let i = 1; i <= 4; i++)
		await page.getByLabel(`Tiebreaker ${i}:`, { exact: true }).selectOption('');
	await page.getByRole('button', { name: 'Save setup', exact: true }).click();
	const groupStageId = await page.getByLabel('Stage', { exact: true }).inputValue();
	await page.goto(`${workspace}?tab=setup&stage=${groupStageId}`);
	await expect(page.getByRole('link', { name: 'Advancement rules', exact: true })).toHaveCount(0);
	await page.getByRole('link', { name: 'Edit stage', exact: true }).click();
	await expect(page.getByLabel('Number of groups')).toHaveValue('3');
	await expect(page.getByLabel('Group 3 entrants')).toHaveValue('2');
	await expect(page.getByLabel('Group 3 qualifiers')).toHaveValue('2');
	await page.goto(`${workspace}?tab=setup&stage=${groupStageId}`);
	await page.getByRole('link', { name: 'Add stage', exact: true }).click();
	await page.getByLabel('Stage name').fill('Playoffs');
	await expect(page.getByLabel('Entrants advancing to the next stage')).toHaveValue('');
	await page.getByLabel('Games per match:', { exact: true }).fill('1');
	await page.getByRole('button', { name: 'Save setup', exact: true }).click();
	await expect(page.getByLabel('Stage', { exact: true }).locator('option')).toHaveCount(2);
	const options = await page
		.getByLabel('Stage', { exact: true })
		.locator('option')
		.evaluateAll((items) =>
			items.map((item) => ({ id: (item as HTMLOptionElement).value, text: item.textContent }))
		);
	const playoffStageId = options.find((item) => item.text?.includes('Playoffs'))!.id;
	await page.goto(`${workspace}?tab=setup&stage=${groupStageId}`);
	await page.getByRole('link', { name: /Continue\s*:\s*Choose entrants/ }).click();
	for (let i = 1; i <= 8; i++) await page.getByLabel(`MS Team ${i}`, { exact: true }).check();
	await page.getByRole('button', { name: 'Save entrants', exact: true }).click();
	await page.goto(`${workspace}?tab=setup&stage=${groupStageId}`);
	await page.getByRole('link', { name: 'Edit stage', exact: true }).first().click();
	await page.getByLabel('Group 1 entrants').selectOption('2');
	await expect(page.locator('[data-group-summary]')).toContainText('must total 8');
	await page.getByLabel('Group 1 entrants').selectOption('3');
	await expect(page.locator('[data-group-summary]')).toHaveText('8 entrants · 6 qualify');
	await page.goto(`${workspace}?tab=setup&stage=${groupStageId}`);
	await page.getByRole('link', { name: /Continue\s*:\s*Seed the bracket/ }).click();
	await page.getByLabel('Group allocation').selectOption('MANUAL');
	const assignments = page.locator('select[name^="group_"]');
	for (let i = 0; i < 8; i++)
		await assignments.nth(i).selectOption(String(i < 3 ? 1 : i < 6 ? 2 : 3));
	await page.getByRole('button', { name: 'Save and preview bracket', exact: true }).click();
	await page.goto(`${workspace}?tab=setup&stage=${groupStageId}`);
	await page.getByRole('link', { name: /Continue\s*:\s*Publish/ }).click();
	await expect(page.getByText(/First publication locks the whole stage plan/)).toBeVisible();
	await page.getByRole('button', { name: 'Publish bracket', exact: true }).click();
	const snapshot = async (): Promise<PublicCompetition> => (await page.request.get(apiUrl)).json();
	expect((await snapshot()).stages).toHaveLength(1);
	await page.goto(`${workspace}?stage=${playoffStageId}`);
	await expect(
		page.getByRole('link', { name: 'Generate next stage draw', exact: true })
	).toHaveCount(0);
	const ordinary = (await snapshot()).stages[0].rounds.flatMap((round) => round.matches);
	async function score(id: number, first: number, second: number, correction = false) {
		await page.goto(`http://127.0.0.1:8015/admin/competitions/match/${id}/change/`);
		await page
			.getByRole('link', { name: correction ? 'Correct result' : 'Enter result', exact: true })
			.click();
		await page.locator('[name="side_one_score"]').fill(String(first));
		await page.locator('[name="side_two_score"]').fill(String(second));
		await page
			.getByRole('button', { name: correction ? 'Preview correction' : 'Save result', exact: true })
			.click();
	}
	for (const match of ordinary) await score(match.id, 1, 1);
	for (const groupId of (await snapshot()).stages[0].groups!.slice(0, 2).map((group) => group.id)) {
		await page.goto(`${workspace}?tab=standings&stage=${groupStageId}&group=${groupId}`);
		await page.getByRole('link', { name: 'Resolve qualification tie', exact: true }).click();
		await page.getByLabel('Resolve qualification tie').selectOption('MANUAL');
		await page.getByRole('button', { name: 'Preview tie choice', exact: true }).click();
		await page.getByLabel('Private organizer reason').fill('PRIVATE-MS-TIE');
		await page.getByRole('button', { name: 'Confirm qualification tie', exact: true }).click();
	}
	await page.goto(`${workspace}?stage=${playoffStageId}`);
	await page.getByRole('link', { name: 'Generate next stage draw', exact: true }).click();
	await page.getByRole('button', { name: 'Generate and preview draw', exact: true }).click();
	await expect(page.getByText('Private preview', { exact: true })).toBeVisible();
	expect((await snapshot()).stages).toHaveLength(1);
	const previewNames = await page.locator('.cw-slot-name').allTextContents();
	await page.reload();
	expect(await page.locator('.cw-slot-name').allTextContents()).toEqual(previewNames);
	await page.getByRole('link', { name: /Publish saved draw/ }).click();
	await page.getByRole('button', { name: 'Publish bracket', exact: true }).click();
	const playoffs = (await snapshot()).stages.find((stage) => stage.id === Number(playoffStageId))!;
	expect(playoffs.entries).toHaveLength(6);
	const played = playoffs.rounds
		.flatMap((round) => round.matches)
		.find((match) => match.status === 'PENDING')!;
	await score(played.id, 1, 0);
	await score(ordinary[0].id, 2, 0, true);
	await expect(
		page.getByRole('heading', { name: 'Downstream draws leaving the active competition' })
	).toBeVisible();
	await page.getByLabel('Reason for correction').fill('PRIVATE-MS-CORRECTION');
	await page.getByRole('button', { name: 'Confirm correction and resets', exact: true }).click();
	const retired = (await snapshot()).stages.find((stage) => stage.id === Number(playoffStageId))!;
	expect(retired.draw_state).toBe('AWAITING_REPLACEMENT');
	expect(retired.rounds).toEqual([]);
	const historical = await (
		await page.request.get(`http://127.0.0.1:8015/api/competition-matches/${played.id}/`)
	).json();
	expect(historical.historical).toBe(true);
	expect([historical.side_one_score, historical.side_two_score]).toEqual([1, 0]);
	const spectator = await context.newPage();
	await spectator.setViewportSize({ width: 390, height: 844 });
	await spectator.goto(
		`/en/tournaments/multi-stage-journey-test/games/${division.id}/bracket?stage=${playoffStageId}`
	);
	await expect(spectator.getByText('Awaiting replacement draw', { exact: true })).toBeVisible();
	await expect(spectator.getByText(/Playoffs-M/).first()).toBeVisible();
	expect(await spectator.locator('body').textContent()).not.toContain('PRIVATE-MS');
	expect(await spectator.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto(`${workspace}?tab=setup&stage=${playoffStageId}`);
	expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
	await spectator.close();
});

for (const scenario of [
	{ slug: 'swiss-workflow', count: 9, threshold: false },
	{ slug: 'swiss-repeat', count: 4, threshold: true }
]) {
	test(`Swiss organizers complete ${scenario.threshold ? 'threshold → Swiss → playoffs with repeat consent' : 'odd fixed → playoffs'} and preserve corrected history`, async ({
		page,
		context
	}) => {
		test.setTimeout(240_000);
		page.setDefaultTimeout(10_000);
		const tournamentResponse = await page.request.get(
			'http://127.0.0.1:8015/api/tournaments/swiss-journey-test/'
		);
		expect(tournamentResponse.status()).toBe(200);
		const tournament = await tournamentResponse.json();
		const division = tournament.tournament_games.find(
			(game: { game_slug: string }) => game.game_slug === scenario.slug
		);
		const apiUrl = `http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`;
		await page.goto(`http://127.0.0.1:8015/admin/competitions/competition/create/${division.id}/`);
		await page.getByLabel('Email', { exact: false }).fill('journey-organizer@example.test');
		await page.getByLabel('Password', { exact: false }).fill('Journey-test-password-2026');
		await page.getByRole('button', { name: /Log in/ }).click();
		await page.getByRole('button', { name: 'Continue to setup', exact: true }).click();
		const workspace = page.url().split('?')[0];
		await page.getByRole('link', { name: /Continue\s*:\s*Set up/ }).click();
		const configureUrl = page.url();
		await page.getByLabel('Format:', { exact: true }).selectOption('ROUND_ROBIN');
		await expect(page.getByLabel('Group sizes', { exact: false })).toBeVisible();
		await page.getByLabel('Group sizes', { exact: false }).selectOption('AUTOMATIC');
		await expect(page.getByLabel('Group 1 entrants')).toBeHidden();
		await expect(page.getByLabel('Group 1 entrants')).toBeDisabled();
		await expect(page.getByLabel('Group 1 qualifiers')).toBeVisible();
		await page.getByLabel('Group sizes', { exact: false }).selectOption('EXACT');
		await expect(page.getByLabel('Group 1 entrants')).toBeVisible();
		await expect(page.getByLabel('Group 1 entrants')).toBeEnabled();
		await page.getByLabel('Format:', { exact: true }).selectOption('SWISS_FIXED');
		for (const [index, value] of ['OPPONENT_POINTS', 'GAME_DIFFERENCE', 'GAMES_WON', ''].entries())
			await expect(page.locator(`[name="tiebreak_${index + 1}"]`)).toHaveValue(value);
		await page.getByLabel('Format:', { exact: true }).selectOption('ROUND_ROBIN');
		await expect(page.locator('[name="tiebreak_1"]')).toHaveValue('HEAD_TO_HEAD');
		await page
			.getByLabel('Format:', { exact: true })
			.selectOption(scenario.threshold ? 'SWISS_THRESHOLD' : 'SWISS_FIXED');
		await expect(page.locator('[name="tiebreak_1"]')).toHaveValue('OPPONENT_POINTS');
		await page.getByLabel('Stage name').fill('Swiss1');
		await page.getByLabel('Games per match:', { exact: true }).fill(scenario.threshold ? '1' : '2');
		if (scenario.threshold) {
			await page.getByLabel('Wins to qualify').fill('2');
			await page.getByLabel('Losses to eliminate').fill('2');
		} else {
			await page.getByLabel('Series mode').selectOption('FIXED_GAMES');
			await page.getByLabel('Round policy').selectOption('CUSTOM');
			await page.getByLabel('Custom rounds', { exact: false }).fill('4');
			await page.getByLabel('Round policy').selectOption('AUTOMATIC');
			await expect(page.locator('[name="round_count"]')).toBeHidden();
			await page.getByLabel('Round policy').selectOption('CUSTOM');
			await expect(page.locator('[name="round_count"]')).toHaveValue('4');
			await page.locator('[name="advancement_count"]').selectOption('4');
			for (let index = 1; index <= 4; index++)
				await page.locator(`[name="tiebreak_${index}"]`).selectOption('');
		}
		await page.getByRole('button', { name: 'Save setup', exact: true }).click();
		const sourceId = await page.getByLabel('Stage', { exact: true }).inputValue();
		if (scenario.threshold) {
			await page.goto(`${workspace}?tab=setup&stage=${sourceId}`);
			await page.getByRole('link', { name: 'Add stage', exact: true }).click();
			await page.getByLabel('Format:', { exact: true }).selectOption('SWISS_FIXED');
			await page.getByLabel('Stage name').fill('Swiss2');
			await expect(page.getByText(/Pending ceil\(log2\(actual N\)\)/)).toBeVisible();
			await page.locator('[name="advancement_count"]').selectOption('2');
			await page.getByLabel('Games per match:', { exact: true }).fill('1');
			await page.getByRole('button', { name: 'Save setup', exact: true }).click();
		}
		await page.goto(`${workspace}?tab=setup`);
		await page.getByRole('link', { name: 'Add stage', exact: true }).click();
		await page.getByLabel('Format:', { exact: true }).selectOption('SINGLE_ELIMINATION');
		await page.getByLabel('Stage name').fill('Playoffs');
		await page.getByLabel('Games per match:', { exact: true }).fill('1');
		await page.getByRole('button', { name: 'Save setup', exact: true }).click();
		await expect(page.getByLabel('Stage', { exact: true }).locator('option')).toHaveCount(
			scenario.threshold ? 3 : 2
		);
		const stageIds = await page
			.getByLabel('Stage', { exact: true })
			.locator('option')
			.evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value));
		await page.goto(`${workspace}?tab=setup&stage=${sourceId}`);
		await page.getByRole('link', { name: /Continue\s*:\s*Choose entrants/ }).click();
		for (let index = 1; index <= scenario.count; index++)
			await page.getByLabel(`Swiss Team ${index}`, { exact: true }).check();
		await page.getByRole('button', { name: 'Save entrants', exact: true }).click();
		await page.goto(`${workspace}?tab=setup&stage=${sourceId}`);
		await page.getByRole('link', { name: /Continue\s*:\s*Seed the bracket/ }).click();
		await page.getByRole('button', { name: 'Save and preview bracket', exact: true }).click();
		await expect(page.getByText('Private preview', { exact: true }).first()).toBeVisible();
		expect((await page.request.get(apiUrl)).status()).toBe(404);
		const privateNames = await page.locator('.cw-slot-name').allTextContents();
		await page.reload();
		expect(await page.locator('.cw-slot-name').allTextContents()).toEqual(privateNames);
		await page.goto(`${workspace}?tab=setup&stage=${sourceId}`);
		await page.getByRole('link', { name: /Continue\s*:\s*Publish/ }).click();
		await page.getByRole('button', { name: 'Publish bracket', exact: true }).click();
		await page.goto(`${workspace}?tab=setup&stage=${sourceId}`);
		await expect(page.getByRole('link', { name: 'Edit stage', exact: true })).toHaveCount(0);
		await page.goto(configureUrl);
		await page.getByRole('button', { name: 'Save setup', exact: true }).click();
		await expect(page.getByText(/whole stage plan is locked/)).toBeVisible();
		const snapshot = async (): Promise<PublicCompetition> =>
			(await page.request.get(apiUrl)).json();
		const originalRound = (await snapshot()).stages[0].rounds[0];
		async function score(id: number, first: number, second: number, correction = false) {
			await page.goto(`http://127.0.0.1:8015/admin/competitions/match/${id}/change/`);
			await page
				.getByRole('link', { name: correction ? 'Correct result' : 'Enter result', exact: true })
				.click();
			await page.locator('[name="side_one_score"]').fill(String(first));
			await page.locator('[name="side_two_score"]').fill(String(second));
			await page
				.getByRole('button', {
					name: correction ? 'Preview correction' : 'Save result',
					exact: true
				})
				.click();
		}
		const spectator = await context.newPage();
		await spectator.goto(`/en/tournaments/swiss-journey-test/games/${division.id}/bracket`);
		await expect(spectator.getByText('Swiss pairings', { exact: true })).toBeVisible();
		if (!scenario.threshold)
			await expect(spectator.getByText(/^Bye · Swiss Team/).first()).toBeVisible();
		let rematchConfirmed = false;
		for (const stageId of stageIds.slice(0, -1)) {
			if (stageId !== sourceId) {
				await page.goto(`${workspace}?stage=${stageId}`);
				await page.getByRole('link', { name: 'Generate next stage draw', exact: true }).click();
				await page.getByRole('button', { name: 'Generate and preview draw', exact: true }).click();
				expect((await snapshot()).stages).toHaveLength(1);
				await page.getByRole('link', { name: /Publish saved draw/ }).click();
				await page.getByRole('button', { name: 'Publish bracket', exact: true }).click();
			}
			for (let attempt = 0; attempt < 5; attempt++) {
				const stage = (await snapshot()).stages.find((stage) => stage.id === Number(stageId))!;
				const currentRound = stage.rounds
					.filter(
						(round) =>
							!round.matches.some((match) => match.historical) && round.section === 'NORMAL'
					)
					.at(-1)!;
				for (const match of currentRound.matches.filter((match) => match.status !== 'FINAL'))
					await score(match.id, 1, stageId === sourceId && !scenario.threshold ? 1 : 0);
				await page.goto(`${workspace}?tab=standings&stage=${stageId}`);
				const resolve = page.getByRole('link', { name: 'Resolve qualification tie', exact: true });
				if (await resolve.count()) {
					await resolve.click();
					await page.getByLabel('Resolve qualification tie').selectOption('MANUAL');
					await page.getByRole('button', { name: 'Preview tie choice', exact: true }).click();
					await page.getByLabel('Private organizer reason').fill('PRIVATE-SWISS-CUTOFF');
					await page
						.getByRole('button', { name: 'Confirm qualification tie', exact: true })
						.click();
				}
				if (
					(await snapshot()).stages.find((stage) => stage.id === Number(stageId))!.qualification!
						.state === 'RESOLVED'
				)
					break;
				await page.goto(`${workspace}?tab=bracket&stage=${stageId}`);
				await page.getByRole('link', { name: 'Generate next Swiss round', exact: true }).click();
				await page.getByRole('button', { name: 'Generate next Swiss round', exact: true }).click();
				const consent = page.getByRole('link', { name: 'Allow required rematches', exact: true });
				await expect(
					consent.or(page.getByText('Private preview', { exact: true }).first())
				).toBeVisible();
				if (await consent.count()) {
					await consent.click();
					rematchConfirmed = true;
					await expect(page.locator('[name="confirm_rematches"]')).not.toBeChecked();
					await page.locator('[name="confirm_rematches"]').check();
					await page.getByLabel('Private organizer reason').fill('PRIVATE-SWISS-REPEAT');
					await page.getByRole('button', { name: 'Allow required rematches', exact: true }).click();
				}
				await expect(page.getByText('Private preview', { exact: true }).first()).toBeVisible();
				expect(
					(await snapshot()).stages.find((stage) => stage.id === Number(stageId))!.rounds
				).not.toContainEqual(expect.objectContaining({ number: currentRound.number + 1 }));
				const names = await page.locator('.cw-slot-name').allTextContents();
				await page.reload();
				expect(await page.locator('.cw-slot-name').allTextContents()).toEqual(names);
				await page.getByRole('link', { name: 'Publish saved Swiss round', exact: true }).click();
				await page.getByRole('button', { name: 'Publish saved Swiss round', exact: true }).click();
			}
		}
		if (scenario.threshold) expect(rematchConfirmed).toBe(true);
		const playoffId = stageIds.at(-1)!;
		await page.goto(`${workspace}?stage=${playoffId}`);
		await page.getByRole('link', { name: 'Generate next stage draw', exact: true }).click();
		await page.getByRole('button', { name: 'Generate and preview draw', exact: true }).click();
		await page.getByRole('link', { name: /Publish saved draw/ }).click();
		await page.getByRole('button', { name: 'Publish bracket', exact: true }).click();
		const before = await snapshot();
		const played = before.stages
			.find((stage) => stage.id === Number(playoffId))!
			.rounds.flatMap((round) => round.matches)
			.find((match) => match.status === 'PENDING')!;
		await score(played.id, 1, 0);
		const corrected = originalRound.matches.find((match) => match.outcome !== 'BYE')!;
		await score(corrected.id, 0, scenario.threshold ? 1 : 2, true);
		await expect(
			page.getByRole('heading', { name: 'Swiss rounds becoming historical', exact: true })
		).toBeVisible();
		await expect(
			page.getByRole('heading', { name: 'Played Swiss results preserved as history', exact: true })
		).toBeVisible();
		await expect(
			page.getByRole('heading', {
				name: 'Downstream draws leaving the active competition',
				exact: true
			})
		).toBeVisible();
		await page.getByLabel('Reason for correction').fill('PRIVATE-SWISS-CORRECTION');
		await page.getByRole('button', { name: 'Confirm correction and resets', exact: true }).click();
		const after = await snapshot();
		expect(after.stages[0].rounds).toHaveLength(1);
		const current = after.stages[0].rounds[0].matches.find((match) => match.id === corrected.id)!;
		expect([current.side_one_score, current.side_two_score]).toEqual([
			0,
			scenario.threshold ? 1 : 2
		]);
		const retiredSwiss = before.stages[0].rounds[1].matches.find(
			(match) => match.outcome === 'PLAYED'
		)!;
		const retiredSwissDetail = await (
			await page.request.get(`http://127.0.0.1:8015/api/competition-matches/${retiredSwiss.id}/`)
		).json();
		expect(retiredSwissDetail.historical).toBe(true);
		expect([retiredSwissDetail.side_one_score, retiredSwissDetail.side_two_score]).toEqual([
			1,
			scenario.threshold ? 0 : 1
		]);
		expect(after.stages.find((stage) => stage.id === Number(playoffId))!.draw_state).toBe(
			'AWAITING_REPLACEMENT'
		);
		const history = await (
			await page.request.get(`http://127.0.0.1:8015/api/competition-matches/${played.id}/`)
		).json();
		expect(history.historical).toBe(true);
		expect([history.side_one_score, history.side_two_score]).toEqual([1, 0]);
		expect(JSON.stringify(after)).not.toContain('PRIVATE-SWISS');
		const changes: { results: PublicCompetitionChange[] } = await (
			await page.request.get(`${apiUrl}changes/`)
		).json();
		expect(JSON.stringify(changes)).not.toContain('PRIVATE-SWISS');
		const correction = changes.results.find((change) => change.kind === 'result_corrected')!;
		const retained = correction.reset_matches!.find((match) =>
			correction.swiss_impact!.retired_match_ids.includes(match.match_id)
		)!;
		await spectator.reload();
		const historyLink = spectator.getByRole('link', {
			name: `Historical match ${retained.match_code}`,
			exact: true
		});
		await expect(historyLink).toHaveAttribute(
			'href',
			`#change-${correction.revision}-match-${retained.match_id}`
		);
		await historyLink.click();
		await expect(spectator.locator(new URL(spectator.url()).hash)).toBeVisible();
		await spectator.setViewportSize({ width: 390, height: 844 });
		await spectator.goto(
			`/vi/tournaments/swiss-journey-test/games/${division.id}/bracket?stage=${sourceId}`
		);
		await expect(spectator.getByText('Các cặp đấu Swiss', { exact: true })).toBeVisible();
		expect(await spectator.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto(`${workspace}?tab=standings&stage=${sourceId}`);
		const standings = page
			.getByRole('region', { name: 'Swiss standings', exact: true })
			.and(page.locator('[tabindex="0"]'));
		await standings.focus();
		await expect(standings).toBeFocused();
		expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
		await spectator.close();
	});
}
