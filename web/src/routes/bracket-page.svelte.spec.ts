import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import type { PublicCompetition, PublicCompetitionChangesPage } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { resolveDisplayTimeZone } from '$lib/time/tournament-time';
import BracketPage from './tournaments/[slug]/games/[gameId]/bracket/+page.svelte';
import './layout.css';

const displayTimeZone = resolveDisplayTimeZone('Asia/Ho_Chi_Minh');

const competition: PublicCompetition = {
	id: 1,
	competition_revision: 8,
	tournament_game_id: 9,
	tournament_slug: 'summer',
	tournament_name: 'Summer Cup',
	game_name: 'Valorant',
	stages: [
		{
			id: 2,
			sequence: 1,
			name: 'Final bracket',
			format: 'SINGLE_ELIMINATION',
			grand_final_policy: '',
			groups: [],
			round_robin_rules: null,
			series_mode: 'BEST_OF',
			default_series_length: 3,
			status: 'IN_PROGRESS',
			published_at: '2026-09-25T01:00:00Z',
			completed_at: null,
			completed_without_champion: false,
			champion: null,
			entries: [
				{ id: 11, seed: 1, display_name: 'Blue Team', display_tag: 'BLUE' },
				{ id: 12, seed: 2, display_name: 'Red Team', display_tag: 'RED' }
			],
			rounds: [
				{
					id: 3,
					number: 1,
					section: 'main',
					group_id: null,
					tie_resolution_id: null,
					effective_series_mode: 'BEST_OF',
					resting_entry: null,
					series_length_override: null,
					matches: [
						{
							id: 4,
							code: 'R1M1',
							number: 1,
							scheduled_at: '2026-09-25T08:00:00Z',
							status: 'LIVE',
							outcome: '',
							effective_series_length: 3,
							effective_series_mode: 'BEST_OF',
							side_one_score: 1,
							side_two_score: 0,
							started_at: '2026-09-25T08:00:00Z',
							completed_at: null,
							historical: false,
							winner: null,
							slots: [
								{
									position: 1,
									is_resolved: true,
									is_empty: false,
									source_match_id: null,
									source_outcome: '',
									entry: { id: 11, seed: 1, display_name: 'Blue Team', display_tag: 'BLUE' }
								},
								{
									position: 2,
									is_resolved: true,
									is_empty: false,
									source_match_id: null,
									source_outcome: '',
									entry: { id: 12, seed: 2, display_name: 'Red Team', display_tag: 'RED' }
								}
							]
						}
					]
				}
			]
		}
	]
};

const changes: PublicCompetitionChangesPage = {
	next: null,
	previous: null,
	competition_revision: 8,
	results: [
		{
			revision: 8,
			created_at: '2026-09-25T09:00:00Z',
			kind: 'result_corrected',
			match_id: 4,
			match_code: 'R1M1',
			reset_matches: []
		}
	]
};

function doubleElimination(resetStatus: 'CONDITIONAL' | 'PENDING' | 'NOT_REQUIRED') {
	const value = structuredClone(competition);
	const stage = value.stages[0];
	stage.format = 'DOUBLE_ELIMINATION';
	stage.grand_final_policy = 'RESET';
	const baseMatch = stage.rounds[0].matches[0];
	const match = (
		id: number,
		code: string,
		status: 'PENDING' | 'CONDITIONAL' | 'NOT_REQUIRED',
		sourceMatchId: number | null = null,
		sourceOutcome: '' | 'WINNER' | 'LOSER' = ''
	) => ({
		...structuredClone(baseMatch),
		id,
		code,
		status,
		slots: structuredClone(baseMatch.slots).map((slot, index) => ({
			...slot,
			is_resolved: sourceMatchId === null,
			entry: sourceMatchId === null ? slot.entry : null,
			source_match_id: index === 0 ? sourceMatchId : null,
			source_outcome: index === 0 ? sourceOutcome : ''
		}))
	});
	stage.rounds = [
		{
			...structuredClone(stage.rounds[0]),
			id: 21,
			number: 1,
			section: 'UPPER',
			series_length_override: null,
			matches: [match(31, 'U1', 'PENDING')]
		},
		{
			...structuredClone(stage.rounds[0]),
			id: 22,
			number: 1,
			section: 'LOWER',
			series_length_override: null,
			matches: [match(32, 'L1', 'PENDING', 31, 'LOSER')]
		},
		{
			...structuredClone(stage.rounds[0]),
			id: 23,
			number: 1,
			section: 'FINALS',
			series_length_override: null,
			matches: [match(33, 'F1', 'PENDING', 31, 'WINNER')]
		},
		{
			...structuredClone(stage.rounds[0]),
			id: 24,
			number: 2,
			section: 'FINALS',
			series_length_override: null,
			matches: [match(34, 'F2', resetStatus, 33, 'LOSER')]
		}
	];
	return value;
}

function data(overrides: Partial<PublicCompetition> = {}) {
	return {
		state: 'ready' as const,
		slug: 'summer',
		gameId: 9,
		competition: { ...competition, ...overrides },
		changes,
		displayTimeZone
	};
}

beforeEach(() => overwriteGetLocale(() => 'en'));
afterEach(() => overwriteGetLocale(() => 'en'));

describe('public bracket page', () => {
	it('renders an unpublished bracket as an ordinary unavailable state', async () => {
		render(BracketPage, {
			data: { state: 'unavailable', slug: 'summer', gameId: 9, displayTimeZone }
		} as never);

		await expect.element(page.getByRole('heading', { name: 'Tournament bracket' })).toBeVisible();
		await expect.element(page.getByRole('status')).toHaveTextContent('has not been published');
	});

	it('renders ready and live matches in desktop and mobile reading order', async () => {
		const readyCompetition = structuredClone(competition);
		readyCompetition.stages[0].status = 'READY';
		readyCompetition.stages[0].rounds[0].matches[0].status = 'PENDING';
		const readyRender = render(BracketPage, { data: data(readyCompetition) } as never);
		await expect.element(page.getByText('Ready', { exact: true })).toBeVisible();
		await readyRender.unmount();

		const { container } = render(BracketPage, { data: data() } as never);
		await expect.element(page.getByText('In progress', { exact: true })).toBeVisible();
		await expect.element(page.getByText('Live', { exact: true }).last()).toBeVisible();
		await expect.element(page.getByText('Blue Team (BLUE)').last()).toBeVisible();
		await expect.element(page.getByText('Best of 3').last()).toBeVisible();
		expect(container.querySelector('.desktop-bracket')).not.toBeNull();
		expect(container.querySelector('.mobile-bracket')).not.toBeNull();
		expect(container.querySelector('[role="region"]')).toHaveAttribute('tabindex', '0');

		const backLink = container.querySelector<HTMLElement>('a')!;
		backLink.focus();
		expect(document.activeElement).toBe(backLink);
	});

	it.each([0, 1])(
		'labels a forfeit with winning slot index %s as W and FF',
		async (winnerIndex) => {
			const forfeited = structuredClone(competition);
			const match = forfeited.stages[0].rounds[0].matches[0];
			match.status = 'FINAL';
			match.outcome = 'FORFEIT';
			match.winner = match.slots[winnerIndex].entry;
			const { container } = render(BracketPage, { data: data(forfeited) } as never);

			const entrants = container.querySelectorAll('.bracket-match article ul');
			expect(entrants).toHaveLength(2); // Desktop and mobile cards share the result.
			for (const list of entrants) {
				expect(Array.from(list.children, (row) => row.lastElementChild?.textContent)).toEqual(
					winnerIndex === 0 ? ['W', 'FF'] : ['FF', 'W']
				);
			}
		}
	);

	it('renders completion and public correction history', async () => {
		const complete = structuredClone(competition);
		complete.stages[0].status = 'COMPLETE';
		complete.stages[0].completed_at = '2026-09-25T10:00:00Z';
		complete.stages[0].champion = {
			id: 11,
			display_name: 'Blue Team',
			display_tag: 'BLUE'
		};

		const completeRender = render(BracketPage, { data: data(complete) } as never);

		await expect.element(page.getByText('Complete', { exact: true })).toBeVisible();
		await expect.element(page.getByRole('heading', { name: 'Champion' })).toBeVisible();
		await expect.element(page.getByText('Match M1 (Final) result corrected')).toBeVisible();
		await completeRender.unmount();

		complete.stages[0].champion = null;
		complete.stages[0].completed_without_champion = true;
		render(BracketPage, { data: data(complete) } as never);
		await expect.element(page.getByText('No champion', { exact: true })).toBeVisible();
	});

	it('groups double elimination sections and explains all reset states', async () => {
		for (const [status, label] of [
			['CONDITIONAL', 'If needed'],
			['PENDING', 'Pending'],
			['NOT_REQUIRED', 'Not required']
		] as const) {
			const rendered = render(BracketPage, { data: data(doubleElimination(status)) } as never);
			await expect
				.element(page.getByRole('heading', { name: 'Upper bracket' }).last())
				.toBeVisible();
			await expect
				.element(page.getByRole('heading', { name: 'Lower bracket' }).last())
				.toBeVisible();
			await expect.element(page.getByRole('heading', { name: 'Finals' }).last()).toBeVisible();
			await expect.element(page.getByText('Loser of M1', { exact: true }).last()).toBeVisible();
			await expect.element(page.getByText('Winner of M1', { exact: true }).last()).toBeVisible();
			await expect.element(page.getByText(label, { exact: true }).last()).toBeVisible();
			await expect
				.element(
					page.getByText(
						'A reset final is played if the lower-bracket winner wins the first final.'
					)
				)
				.toBeVisible();
			await rendered.unmount();
		}
	});

	it('numbers single-elimination matches across rounds and includes byes', async () => {
		const value = structuredClone(competition);
		const stage = value.stages[0];
		const firstRound = stage.rounds[0];
		const firstMatch = firstRound.matches[0];
		firstMatch.status = 'FINAL';
		firstMatch.outcome = 'BYE';
		firstMatch.slots[1].is_empty = true;
		firstMatch.slots[1].entry = null;
		firstRound.matches.push({ ...structuredClone(firstMatch), id: 5, code: 'R1M2', number: 2 });
		stage.rounds.push({
			...structuredClone(firstRound),
			id: 6,
			number: 2,
			matches: [{ ...structuredClone(firstMatch), id: 7, code: 'R2M1', number: 1 }]
		});
		const { container } = render(BracketPage, { data: data(value) } as never);

		for (const layout of ['desktop', 'mobile']) {
			expect(
				Array.from(container.querySelectorAll(`.${layout}-bracket article h3`), (heading) =>
					heading.textContent?.trim()
				)
			).toEqual(['M1', 'M2', 'M3']);
		}
		expect(container.textContent).toContain('Match M1 (Round 1) result corrected');
		expect(container.querySelector('article ul')).toHaveAttribute(
			'aria-label',
			'Entrants for match M1'
		);
	});

	it.each(['en', 'vi'] as const)(
		'uses one sequence for every double-elimination section and log action in %s',
		async (locale) => {
			overwriteGetLocale(() => locale);
			const value = doubleElimination('CONDITIONAL');
			const rounds = value.stages[0].rounds;
			const upper = rounds[0];
			upper.matches.push({ ...structuredClone(upper.matches[0]), id: 35, code: 'U2', number: 2 });
			const upperFinal = {
				...structuredClone(upper),
				id: 25,
				number: 2,
				matches: [{ ...structuredClone(upper.matches[0]), id: 36, code: 'U3', number: 1 }]
			};
			// The API orders rounds by round number, interleaving bracket sections.
			value.stages[0].rounds = [...rounds.slice(0, 3), upperFinal, rounds[3]];
			const log = structuredClone(changes);
			log.results = [
				'match_scheduled',
				'match_series_length_changed',
				'match_started',
				'match_progress_saved',
				'match_finalized',
				'result_corrected'
			].map((kind, index) => ({
				...log.results[0],
				kind,
				revision: index + 1,
				match_id: 31,
				match_code: 'U1'
			}));
			log.results.push({ ...log.results[4], revision: 7, match_id: 34, match_code: 'F2' });
			const { container } = render(BracketPage, {
				data: { ...data(value), changes: log }
			} as never);

			for (const layout of ['desktop', 'mobile']) {
				expect(
					Array.from(container.querySelectorAll(`.${layout}-bracket article h3`), (heading) =>
						heading.textContent?.trim()
					)
				).toEqual(['M1', 'M2', 'M3', 'M4', 'M5', 'M6']);
			}
			const logItems = container.querySelectorAll(
				'section[aria-labelledby="bracket-changes-heading"] > ol > li'
			);
			for (const item of Array.from(logItems).slice(0, 6)) {
				expect(item.textContent).toContain(
					locale === 'en' ? 'M1 (Upper bracket Round 1)' : 'M1 (Nhánh thắng Vòng 1)'
				);
			}
			expect(logItems[4].textContent).toContain(
				locale === 'en'
					? 'Match M1 (Upper bracket Round 1) has ended'
					: 'Trận M1 (Nhánh thắng Vòng 1) đã kết thúc'
			);
			expect(logItems[6].textContent).toContain(
				locale === 'en'
					? 'Match M6 (Reset final) has ended'
					: 'Trận M6 (Chung kết tái đấu) đã kết thúc'
			);
		}
	);

	it.each(['en', 'vi'] as const)('renders retained correction snapshots in %s', async (locale) => {
		overwriteGetLocale(() => locale);
		const correctionChanges = structuredClone(changes);
		correctionChanges.results[0] = {
			...correctionChanges.results[0],
			match_id: 33,
			match_code: 'F1',
			before: {
				match_id: 33,
				match_code: 'F1',
				status: 'FINAL',
				outcome: 'PLAYED',
				side_one: 'Blue Team',
				side_two: 'Red Team',
				side_one_score: 2,
				side_two_score: 0,
				winner: 'Blue Team',
				applied_series_length: 3,
				started_at: null,
				completed_at: null
			},
			after: {
				match_id: 33,
				match_code: 'F1',
				status: 'FINAL',
				outcome: 'DOUBLE_FORFEIT',
				side_one: 'Blue Team',
				side_two: 'Red Team',
				side_one_score: 1,
				side_two_score: 0,
				winner: null,
				applied_series_length: 3,
				started_at: null,
				completed_at: null
			},
			reset_matches: [
				{
					match_id: 34,
					match_code: 'F2',
					status: 'FINAL',
					outcome: 'PLAYED',
					side_one: 'Blue Team',
					side_two: 'Red Team',
					side_one_score: 2,
					side_two_score: 1,
					winner: 'Blue Team',
					applied_series_length: 3,
					started_at: null,
					completed_at: null
				}
			],
			reset_final_changes: [
				{ match_id: 34, match_code: 'F2', before: 'CONDITIONAL', after: 'ACTIVE' }
			]
		};

		correctionChanges.results[0].reset_matches!.push({
			...correctionChanges.results[0].reset_matches![0],
			match_id: 32,
			match_code: 'L1',
			status: 'LIVE',
			outcome: '',
			side_one_score: 1,
			side_two_score: null,
			winner: null
		});
		const { container } = render(BracketPage, {
			data: { ...data(doubleElimination('PENDING')), changes: correctionChanges }
		} as never);

		const expected =
			locale === 'en'
				? [
						'Before: Played · Blue Team 2–0 Red Team · Blue Team won',
						'After: Double forfeit · Blue Team 1–0 Red Team · No winner',
						'M4: Played · Blue Team 2–1 Red Team · Blue Team won',
						'M2: Live · Blue Team 1–— Red Team · No winner',
						'Affected matches: M4, M2',
						'M4: If needed → Active'
					]
				: [
						'Trước: Đã thi đấu · Blue Team 2–0 Red Team · Blue Team thắng',
						'Sau: Cả hai bị xử thua · Blue Team 1–0 Red Team · Không có đội thắng',
						'M4: Đã thi đấu · Blue Team 2–1 Red Team · Blue Team thắng',
						'M2: Trực tiếp · Blue Team 1–— Red Team · Không có đội thắng',
						'Các trận bị ảnh hưởng: M4, M2',
						'M4: Nếu cần → Đang áp dụng'
					];
		for (const summary of expected) expect.soft(container.textContent).toContain(summary);
	});

	it('renders the bracket in Vietnamese', async () => {
		overwriteGetLocale(() => 'vi');
		render(BracketPage, { data: data() } as never);

		await expect.element(page.getByRole('heading', { name: 'Valorant · Nhánh đấu' })).toBeVisible();
		await expect.element(page.getByText('Đang diễn ra', { exact: true })).toBeVisible();
		await expect.element(page.getByText('Đã sửa kết quả trận M1 (Chung kết)')).toBeVisible();
	});
});

function roundRobinCompetition() {
	const value = structuredClone(competition);
	const stage = value.stages[0];
	stage.format = 'ROUND_ROBIN';
	stage.series_mode = 'FIXED_GAMES';
	stage.default_series_length = 2;
	stage.status = 'AWAITING';
	stage.round_robin_rules = {
		meetings: 1,
		win_points: '2.50',
		draw_points: '0.75',
		loss_points: '0.25',
		tiebreaks: ['HEAD_TO_HEAD', 'GAME_DIFFERENCE']
	};
	const entries = [
		stage.rounds[0].matches[0].slots[0].entry!,
		stage.rounds[0].matches[0].slots[1].entry!,
		{ id: 13, seed: 3, display_name: 'Green Team', display_tag: '' }
	];
	stage.entries = entries;
	stage.groups = [1, 2].map((id) => ({
		id,
		number: id,
		name: id === 1 ? 'Alpha' : 'Beta',
		qualifying_places: 1,
		entries:
			id === 1
				? entries
				: [
						...entries,
						{ id: 14, seed: 4, display_name: 'Gold Team', display_tag: '' },
						{ id: 15, seed: 5, display_name: 'Silver Team', display_tag: '' }
					],
		round_ids: id === 1 ? [3, 10] : [],
		standings: entries.map((entry) => ({
			entry,
			rank: 1,
			played: 2,
			wins: 0,
			draws: 2,
			losses: 0,
			points: '1.50',
			games_won: 2,
			game_difference: 0,
			qualification: 'TIED' as const
		})),
		qualifiers: [],
		qualification_state: 'AWAITING_RESOLUTION' as const,
		tie_resolutions:
			id === 1
				? [
						{
							id: 8,
							parent_id: null,
							method: 'EXTRA_MATCHES' as const,
							state: 'SUPERSEDED' as const,
							tied_entries: entries,
							places: 1,
							ordered_entries: [],
							round_ids: [10]
						}
					]
				: []
	}));
	const round = stage.rounds[0];
	round.group_id = 1;
	round.effective_series_mode = 'FIXED_GAMES';
	round.resting_entry = entries[2];
	Object.assign(round.matches[0], {
		status: 'FINAL',
		outcome: 'PLAYED',
		winner: null,
		side_one_score: 1,
		side_two_score: 1,
		effective_series_mode: 'FIXED_GAMES',
		effective_series_length: 2
	});
	stage.rounds.push({
		...structuredClone(round),
		id: 10,
		section: 'TIEBREAK',
		tie_resolution_id: 8,
		resting_entry: null,
		effective_series_mode: 'BEST_OF',
		matches: [
			{
				...structuredClone(round.matches[0]),
				id: 99,
				historical: true,
				effective_series_mode: 'BEST_OF',
				effective_series_length: 1,
				side_one_score: 1,
				side_two_score: 0,
				winner: entries[0]
			}
		]
	});
	return value;
}

describe('public round robin groups', () => {
	it.each(['en', 'vi'] as const)(
		'shows tied ranks, decimal points, fixed draws, rests and retained contests in %s',
		async (locale) => {
			overwriteGetLocale(() => locale);
			const { container } = render(BracketPage, { data: data(roundRobinCompetition()) } as never);
			await expect.element(page.getByRole('table')).toBeVisible();
			expect(container.querySelectorAll('tbody tr')).toHaveLength(3);
			expect(
				Array.from(container.querySelectorAll('tbody tr td:first-child'), (cell) =>
					cell.textContent?.trim()
				)
			).toEqual(['1', '1', '1']);
			expect(container.textContent).toContain('1.50');
			expect(container.textContent).toContain(locale === 'en' ? 'Fixed 2 games' : 'Cố định 2 ván');
			expect(container.textContent).toContain(
				locale === 'en' ? 'Rest: Green Team' : 'Nghỉ lượt: Green Team'
			);
			expect(container.textContent).toContain(locale === 'en' ? 'Draw' : 'Hòa');
			expect(container.textContent).toContain(locale === 'en' ? 'Historical' : 'Lịch sử');
			expect(container.textContent).toContain(
				locale === 'en' ? 'Awaiting qualification resolution' : 'Chờ phân định suất đi tiếp'
			);
			const selector = container.querySelector<HTMLSelectElement>('select')!;
			expect(selector.options).toHaveLength(2);
			selector.focus();
			expect(document.activeElement).toBe(selector);
			selector.value = '2';
			selector.dispatchEvent(new Event('change', { bubbles: true }));
			await expect
				.element(
					page.getByRole('heading', {
						name: locale === 'en' ? 'Beta · Standings' : 'Beta · Bảng xếp hạng'
					})
				)
				.toBeVisible();
		}
	);

	it('shows an explicit manual qualifier after refreshed data', async () => {
		const value = roundRobinCompetition();
		const group = value.stages[0].groups[0];
		group.qualification_state = 'RESOLVED';
		group.qualifiers = [group.entries[2]];
		group.standings[2].qualification = 'QUALIFIED';
		group.tie_resolutions.push({
			id: 9,
			parent_id: null,
			method: 'MANUAL',
			state: 'CONFIRMED',
			tied_entries: group.entries,
			places: 1,
			ordered_entries: [group.entries[2], ...group.entries.slice(0, 2)],
			round_ids: []
		});
		render(BracketPage, { data: data(value) } as never);
		await expect.element(page.getByText('Qualified', { exact: true })).toBeVisible();
		await expect.element(page.getByText('Organizer decision', { exact: true })).toBeVisible();
		await expect.element(page.getByText('Green Team → Blue Team → Red Team')).toBeVisible();
	});
});
