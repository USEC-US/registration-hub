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
		const rounds = page.getByLabel(locale === 'en' ? 'Round' : 'Vòng đấu', { exact: true });
		await expect(rounds).toBeEnabled();
		await rounds.focus();
		await page.keyboard.press('Space');
		await page.keyboard.press('End');
		await page.keyboard.press('Enter');
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

test('multi-stage spectators switch unequal groups and playoffs in EN and VI at 390px', async ({
	page
}) => {
	const tournament = await (
		await page.request.get('http://127.0.0.1:8015/api/tournaments/multi-stage-journey-test/')
	).json();
	const division = tournament.tournament_games.find(
		(game: { game_slug: string }) => game.game_slug === 'ms-valorant'
	);
	const competition = await (
		await page.request.get(`http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`)
	).json();
	const [groups, playoffs] = competition.stages;
	await page.setViewportSize({ width: 390, height: 844 });
	for (const locale of ['en', 'vi']) {
		await page.goto(
			`/${locale}/tournaments/multi-stage-journey-test/games/${division.id}/bracket?stage=${groups.id}`
		);
		const stage = page.getByLabel(locale === 'en' ? 'Stage' : 'Giai đoạn', { exact: true });
		await expect(stage).toHaveValue(String(groups.id));
		await expect(page.getByRole('table').locator('tbody tr')).toHaveCount(3);
		const group = page.getByLabel(locale === 'en' ? 'Group' : 'Bảng', { exact: true });
		await expect(group).toBeEnabled();
		await group.focus();
		await page.keyboard.press('Space');
		await page.keyboard.press('End');
		await page.keyboard.press('Enter');
		await expect(page.getByRole('table').locator('tbody tr')).toHaveCount(2);
		await stage.selectOption(String(playoffs.id));
		await expect(group).toHaveCount(0);
		await expect(stage).toHaveValue(String(playoffs.id));
		await expect(page.getByText('Playoffs', { exact: true })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Playoffs-M1', exact: true })).toBeVisible();
		expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
	}
});

test('Swiss spectators read odd byes, threshold qualification and consecutive stage resets in EN and VI', async ({
	page
}) => {
	const response = await page.request.get(
		'http://127.0.0.1:8015/api/tournaments/swiss-journey-test/'
	);
	expect(response.status()).toBe(200);
	const tournament = await response.json();
	for (const slug of ['swiss-chess', 'swiss-valorant']) {
		const division = tournament.tournament_games.find(
			(game: { game_slug: string }) => game.game_slug === slug
		);
		const response = await page.request.get(
			`http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`
		);
		expect(response.status()).toBe(200);
		const competition = await response.json();
		for (const locale of ['en', 'vi']) {
			await page.setViewportSize({ width: 390, height: 844 });
			await page.goto(
				`/${locale}/tournaments/swiss-journey-test/games/${division.id}/bracket?stage=${competition.stages[0].id}`
			);
			await expect(
				page.getByText(locale === 'en' ? 'Swiss pairings' : 'Các cặp đấu Swiss', { exact: true })
			).toBeVisible();
			await expect(
				page.getByText(
					locale === 'en' ? 'Swiss qualification complete' : 'Đã hoàn tất vòng loại Swiss',
					{ exact: true }
				)
			).toBeVisible();
			if (slug === 'swiss-chess') {
				await expect(
					page.getByText(locale === 'en' ? 'Byes' : 'Lượt miễn đấu', { exact: true })
				).toBeVisible();
				await page
					.getByLabel(locale === 'en' ? 'Round' : 'Vòng đấu', { exact: true })
					.selectOption(String(competition.stages[0].rounds[0].id));
				await expect(
					page.getByText(locale === 'en' ? /^Bye · / : /^Miễn đấu · /).first()
				).toBeVisible();
			} else {
				await expect(
					page.getByText(
						locale === 'en'
							? 'Qualify at 3 wins; eliminated at 3 losses.'
							: 'Đi tiếp khi đạt 3 trận thắng; bị loại khi thua 3 trận.',
						{ exact: true }
					)
				).toBeVisible();
				expect(
					competition.stages[0].swiss_standings.some(
						(row: { status: string }) => row.status === 'ELIMINATED'
					)
				).toBe(true);
				await page
					.getByLabel(locale === 'en' ? 'Stage' : 'Giai đoạn', { exact: true })
					.selectOption(String(competition.stages[1].id));
				await expect(
					page.getByText(locale === 'en' ? 'Automatic round limit' : 'Số vòng tự động', {
						exact: true
					})
				).toBeVisible();
				expect(
					competition.stages[1].swiss_standings.every(
						(row: { wins: number; losses: number; draws: number }) =>
							row.wins + row.losses + row.draws <= competition.stages[1].swiss_rules.round_limit
					)
				).toBe(true);
			}
			expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
			expect(await page.locator('body').textContent()).not.toContain('@example.invalid');
			expect(JSON.stringify(competition)).not.toContain(
				'Synthetic Swiss confirmed repeat exception'
			);
		}
	}
});

test('lifecycle spectators read ended outcomes and retained matches in EN and VI at 390px', async ({
	page
}) => {
	const tournament = await (
		await page.request.get('http://127.0.0.1:8015/api/tournaments/dev-usec-lifecycle/')
	).json();
	const division = tournament.tournament_games.find(
		(game: { game_slug: string }) => game.game_slug === 'lifecycle-ended'
	);
	const api = `http://127.0.0.1:8015/api/tournament-games/${division.id}/competition/`;
	const competition = await (await page.request.get(api)).json();
	const changes = await (await page.request.get(`${api}changes/`)).json();
	expect(JSON.stringify({ competition, changes })).not.toContain('PRIVATE-LIFECYCLE');
	expect(JSON.stringify({ competition, changes })).not.toContain('@example.invalid');
	const played = competition.stages[1].rounds
		.flatMap((r: { matches: { id: number; historical: boolean; outcome: string }[] }) => r.matches)
		.find((m: { historical: boolean; outcome: string }) => m.historical && m.outcome === 'PLAYED');
	expect(played).toBeTruthy();
	const event = changes.results.find((change: { reset_matches?: { match_id: number }[] }) =>
		change.reset_matches?.some((match) => match.match_id === played.id)
	);
	expect(event).toBeTruthy();
	const recorded = event.reset_matches.find(
		(match: { match_id: number }) => match.match_id === played.id
	);
	const fragment = `#change-${event.revision}-match-${played.id}`;
	const detail = await (
		await page.request.get(`http://127.0.0.1:8015/api/competition-matches/${played.id}/`)
	).json();
	expect(detail.historical).toBe(true);
	expect([detail.side_one_score, detail.side_two_score]).toEqual([1, 0]);
	await page.setViewportSize({ width: 390, height: 844 });
	for (const locale of ['en', 'vi']) {
		await page.goto(
			`/${locale}/tournaments/dev-usec-lifecycle/games/${division.id}/bracket?stage=${competition.stages[1].id}`
		);
		await expect(
			page
				.getByText(locale === 'en' ? 'Competition ended' : 'Giải đấu đã kết thúc', { exact: true })
				.first()
		).toBeVisible();
		await expect(
			page
				.getByText(locale === 'en' ? 'No champion' : 'Không có nhà vô địch', { exact: true })
				.first()
		).toBeVisible();
		const history = page.getByRole('link', {
			name: `${locale === 'en' ? 'Historical match' : 'Trận lịch sử'} ${recorded.match_code}`,
			exact: true
		});
		await expect(history).toHaveAttribute('href', fragment);
		await expect(history).toBeVisible();
		await history.focus();
		await expect(history).toBeFocused();
		await page.keyboard.press('Enter');
		expect(new URL(page.url()).hash).toBe(fragment);
		await expect(page.locator(fragment)).toBeVisible();
		await expect(page.locator(fragment)).toContainText('1–0');
		expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
	}
});
