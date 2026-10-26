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
	ending: null,
	stages: [
		{
			id: 2,
			sequence: 1,
			name: 'Final bracket',
			draw_state: 'PUBLISHED',
			lifecycle_state: 'OPEN',
			qualification: null,
			format: 'SINGLE_ELIMINATION',
			grand_final_policy: '',
			groups: [],
			round_robin_rules: null,
			swiss_rules: null,
			swiss_standings: [],
			series_mode: 'BEST_OF',
			default_series_length: 3,
			status: 'IN_PROGRESS',
			published_at: '2026-09-25T01:00:00Z',
			completed_at: null,
			completed_without_champion: false,
			champion: null,
			entries: [
				{
					id: 11,
					status: 'ACTIVE' as const,
					seed: 1,
					display_name: 'Blue Team',
					display_tag: 'BLUE'
				},
				{ id: 12, status: 'ACTIVE' as const, seed: 2, display_name: 'Red Team', display_tag: 'RED' }
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
									entry: {
										id: 11,
										status: 'ACTIVE' as const,
										seed: 1,
										display_name: 'Blue Team',
										display_tag: 'BLUE'
									}
								},
								{
									position: 2,
									is_resolved: true,
									is_empty: false,
									source_match_id: null,
									source_outcome: '',
									entry: {
										id: 12,
										status: 'ACTIVE' as const,
										seed: 2,
										display_name: 'Red Team',
										display_tag: 'RED'
									}
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
		await expect.element(page.getByText('Match R1M1 (Final) result corrected')).toBeVisible();
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
			await expect.element(page.getByText('Loser of U1', { exact: true }).last()).toBeVisible();
			await expect.element(page.getByText('Winner of U1', { exact: true }).last()).toBeVisible();
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

	it('preserves stored single-elimination labels including byes', async () => {
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
			).toEqual(['R1M1', 'R1M2', 'R2M1']);
		}
		expect(container.textContent).toContain('Match R1M1 (Round 1) result corrected');
		expect(container.querySelector('article ul')).toHaveAttribute(
			'aria-label',
			'Entrants for match R1M1'
		);
	});

	it.each(['en', 'vi'] as const)(
		'preserves stored labels across double-elimination sections and Changes in %s',
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
				).toEqual(['U1', 'U2', 'U3', 'L1', 'F1', 'F2']);
			}
			const logItems = container.querySelectorAll(
				'section[aria-labelledby="bracket-changes-heading"] > ol > li'
			);
			for (const item of Array.from(logItems).slice(0, 6)) {
				expect(item.textContent).toContain(
					locale === 'en' ? 'U1 (Upper bracket Round 1)' : 'U1 (Nhánh thắng Vòng 1)'
				);
			}
			expect(logItems[4].textContent).toContain(
				locale === 'en'
					? 'Match U1 (Upper bracket Round 1) has ended'
					: 'Trận U1 (Nhánh thắng Vòng 1) đã kết thúc'
			);
			expect(logItems[6].textContent).toContain(
				locale === 'en'
					? 'Match F2 (Reset final) has ended'
					: 'Trận F2 (Chung kết tái đấu) đã kết thúc'
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
						'F2: Played · Blue Team 2–1 Red Team · Blue Team won',
						'L1: Live · Blue Team 1–— Red Team · No winner',
						'Affected matches: F2, L1',
						'F2: If needed → Active'
					]
				: [
						'Trước: Đã thi đấu · Blue Team 2–0 Red Team · Blue Team thắng',
						'Sau: Cả hai bị xử thua · Blue Team 1–0 Red Team · Không có đội thắng',
						'F2: Đã thi đấu · Blue Team 2–1 Red Team · Blue Team thắng',
						'L1: Trực tiếp · Blue Team 1–— Red Team · Không có đội thắng',
						'Các trận bị ảnh hưởng: F2, L1',
						'F2: Nếu cần → Đang áp dụng'
					];
		for (const summary of expected) expect.soft(container.textContent).toContain(summary);
	});

	it('renders the bracket in Vietnamese', async () => {
		overwriteGetLocale(() => 'vi');
		render(BracketPage, { data: data() } as never);

		await expect.element(page.getByRole('heading', { name: 'Valorant · Nhánh đấu' })).toBeVisible();
		await expect.element(page.getByText('Đang diễn ra', { exact: true })).toBeVisible();
		await expect.element(page.getByText('Đã sửa kết quả trận R1M1 (Chung kết)')).toBeVisible();
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
		{ id: 13, status: 'ACTIVE' as const, seed: 3, display_name: 'Green Team', display_tag: '' }
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
						{
							id: 14,
							status: 'ACTIVE' as const,
							seed: 4,
							display_name: 'Gold Team',
							display_tag: ''
						},
						{
							id: 15,
							status: 'ACTIVE' as const,
							seed: 5,
							display_name: 'Silver Team',
							display_tag: ''
						}
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
	round.section = 'NORMAL';
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
	it('bounds rendered cards to one round while retaining historical navigation', async () => {
		const value = roundRobinCompetition();
		const stage = value.stages[0];
		const ordinary = stage.rounds.find((round) => round.section === 'NORMAL')!;
		for (let i = 0; i < 50; i++)
			stage.rounds.push({
				...ordinary,
				id: 100 + i,
				number: 10 + i,
				matches: ordinary.matches.map((match) => ({ ...match, id: 1000 + i }))
			});
		const { container } = render(BracketPage, { data: data(value) } as never);
		await expect.element(page.getByRole('table')).toBeVisible();
		expect(container.querySelectorAll('article')).toHaveLength(ordinary.matches.length);
		const selector = page.getByLabelText('Round', { exact: true });
		await expect.element(selector).toBeEnabled();
		(selector.element() as HTMLSelectElement).value = '10';
		selector.element().dispatchEvent(new Event('change', { bubbles: true }));
		await expect.element(page.getByText('Historical', { exact: true })).toBeVisible();
		expect(container.querySelectorAll('article')).toHaveLength(1);
	});
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
			const rounds = container.querySelector<HTMLSelectElement>('#round-select')!;
			rounds.value = '10';
			rounds.dispatchEvent(new Event('change', { bubbles: true }));
			await expect
				.element(page.getByText(locale === 'en' ? 'Historical' : 'Lịch sử', { exact: true }))
				.toBeVisible();
			expect(container.textContent).toContain(locale === 'en' ? 'Historical' : 'Lịch sử');
			expect(container.textContent).toContain(
				locale === 'en' ? 'Awaiting qualification resolution' : 'Chờ phân định suất đi tiếp'
			);
			const selector = container.querySelector<HTMLSelectElement>('#group-select')!;
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

describe('public multi-stage navigation', () => {
	it('switches stages by identity, keeps selection on refresh, and shows replacement state', async () => {
		const value = roundRobinCompetition();
		const playoffs = structuredClone(competition.stages[0]);
		playoffs.id = 22;
		playoffs.sequence = 2;
		playoffs.name = 'Playoffs';
		playoffs.draw_state = 'AWAITING_REPLACEMENT';
		playoffs.entries = [];
		playoffs.rounds = [];
		value.stages.push(playoffs);
		const { container, rerender } = render(BracketPage, {
			params: { slug: 'summer', gameId: '9' },
			data: {
				state: 'ready',
				slug: 'summer',
				gameId: 9,
				competition: value,
				changes,
				displayTimeZone,
				selectedStageId: value.stages[0].id
			}
		});
		await page.getByRole('combobox', { name: 'Stage', exact: true }).selectOptions('22');
		await expect
			.element(page.getByText('Awaiting replacement draw', { exact: true }))
			.toBeVisible();
		expect(container.querySelector('#group-select')).toBeNull();
		await rerender({
			data: {
				state: 'ready',
				slug: 'summer',
				gameId: 9,
				competition: structuredClone(value),
				changes,
				displayTimeZone,
				selectedStageId: value.stages[0].id
			},
			params: { slug: 'summer', gameId: '9' }
		});
		await expect
			.element(page.getByText('Awaiting replacement draw', { exact: true }))
			.toBeVisible();
		await page
			.getByRole('combobox', { name: 'Stage', exact: true })
			.selectOptions(String(value.stages[0].id));
		await expect.element(page.getByRole('combobox', { name: 'Group', exact: true })).toBeVisible();
	});
});

function swissCompetition(threshold = false) {
	const value = structuredClone(competition);
	const stage = value.stages[0];
	stage.name = 'Swiss qualification';
	stage.format = threshold ? 'SWISS_THRESHOLD' : 'SWISS_FIXED';
	stage.swiss_rules = {
		round_policy: threshold ? 'THRESHOLD' : 'AUTOMATIC',
		round_limit: 3,
		win_target: threshold ? 2 : null,
		loss_limit: threshold ? 2 : null,
		win_points: '3.00',
		draw_points: '1.00',
		loss_points: '0.00',
		tiebreaks: ['OPPONENT_POINTS', 'GAME_DIFFERENCE', 'GAMES_WON']
	};
	stage.entries.push({
		id: 13,
		status: 'ACTIVE' as const,
		seed: 3,
		display_name: 'Green Team',
		display_tag: ''
	});
	const [blue, red, green] = stage.entries;
	stage.swiss_standings = stage.entries.map((entry, index) => ({
		entry,
		rank: index === 2 ? 2 : 1,
		played: threshold ? 2 : 1,
		wins: threshold ? [2, 0, 1][index] : 1,
		draws: 0,
		losses: threshold ? [0, 2, 0][index] : 0,
		points: threshold ? ['6.00', '0.00', '3.00'][index] : '3.00',
		games_won: index === 0 ? 4 : 0,
		game_difference: index === 0 ? 4 : 0,
		opponent_points: index === 2 ? '0.00' : '3.00',
		bye_count: index === 2 ? 1 : 0,
		status: threshold ? (['QUALIFIED', 'ELIMINATED', 'ACTIVE'] as const)[index] : 'ACTIVE'
	}));
	stage.qualification = {
		state: threshold ? 'PROVISIONAL' : 'AWAITING_RESOLUTION',
		advance_count: threshold ? null : 2,
		qualifiers: threshold ? [blue] : [],
		placement_bands: [],
		block_reason: null,
		cutoff_ties: threshold
			? []
			: [
					{
						group_id: null,
						places: 1,
						tied_entries: [red, green],
						resolution_id: null,
						parent_id: null,
						method: null,
						state: 'AWAITING_RESOLUTION',
						ordered_entries: [],
						round_ids: []
					}
				]
	};
	const round = stage.rounds[0];
	round.section = 'NORMAL';
	const match = round.matches[0];
	Object.assign(match, {
		code: 'Swiss qualification-M1',
		status: 'FINAL',
		outcome: 'PLAYED',
		winner: blue,
		side_one_score: 2,
		side_two_score: 0,
		completed_at: '2026-09-25T09:00:00Z'
	});
	const bye = structuredClone(match);
	Object.assign(bye, {
		id: 5,
		code: 'Swiss qualification-M2',
		number: 2,
		outcome: 'BYE',
		winner: green,
		side_one_score: null,
		side_two_score: null
	});
	bye.slots[0].entry = green;
	Object.assign(bye.slots[1], { is_empty: true, entry: null });
	round.matches.push(bye);
	stage.rounds.push({
		...structuredClone(round),
		id: 6,
		number: 2,
		matches: [
			{
				...structuredClone(match),
				id: 7,
				code: 'Swiss qualification-M3',
				status: 'PENDING',
				outcome: '',
				winner: null,
				side_one_score: null,
				side_two_score: null,
				started_at: null,
				completed_at: null,
				slots: match.slots.map((slot, index) => ({ ...slot, entry: index === 0 ? blue : green }))
			}
		]
	});
	const playoffs = structuredClone(competition.stages[0]);
	Object.assign(playoffs, {
		id: 22,
		sequence: 2,
		name: 'Playoffs',
		draw_state: 'AWAITING_REPLACEMENT',
		entries: [],
		rounds: []
	});
	value.stages.push(playoffs);
	return value;
}

describe('public Swiss qualification', () => {
	it.each(['en', 'vi'] as const)(
		'renders fixed rounds, standings and cutoff state in %s',
		async (locale) => {
			overwriteGetLocale(() => locale);
			const { container } = render(BracketPage, { data: data(swissCompetition()) } as never);
			await expect.element(page.getByRole('table')).toBeVisible();
			const standings = container.querySelector('table')!;
			container.style.width = '390px';
			const scroll = container.querySelector<HTMLElement>('.cw-bracket-scroll')!;
			expect(scroll).toHaveAttribute('tabindex', '0');
			expect(scroll.clientWidth).toBeLessThanOrEqual(390);
			expect(scroll.scrollWidth).toBeGreaterThan(scroll.clientWidth);
			const main = container.querySelector('main')!;
			expect(main.scrollWidth).toBeLessThanOrEqual(main.clientWidth);

			expect(standings.textContent).toContain(locale === 'en' ? 'Opponent points' : 'Điểm đối thủ');
			expect(standings.textContent).toContain('3.00');
			expect(standings.textContent).toContain('0.00');
			expect(container.textContent).toContain(
				locale === 'en' ? 'Current round: 2 / 3' : 'Vòng hiện tại: 2 / 3'
			);
			expect(container.textContent).toContain(
				locale === 'en' ? 'Automatic round limit' : 'Số vòng tự động'
			);
			expect(container.textContent).toContain(locale === 'en' ? 'Top 2 advance' : 'Top 2 đi tiếp');
			expect(container.textContent).toContain(
				locale === 'en' ? 'Awaiting qualification resolution' : 'Chờ phân định suất đi tiếp'
			);
			expect(container.querySelectorAll('article')).toHaveLength(1);
			expect(container.querySelector('article h3')?.textContent).toContain(
				'Swiss qualification-M3'
			);
			await page
				.getByRole('combobox', { name: locale === 'en' ? 'Round' : 'Vòng đấu', exact: true })
				.selectOptions('3');
			await expect
				.element(page.getByText(locale === 'en' ? 'Bye' : 'Miễn đấu', { exact: true }))
				.toBeVisible();
			expect(container.querySelectorAll('article')).toHaveLength(2);
			const byeScores = container
				.querySelectorAll('article')[1]
				.querySelectorAll('ul li > span:last-child');
			expect(Array.from(byeScores, (score) => score.textContent?.trim())).toEqual(['—', '—']);
			await expect
				.element(page.getByRole('heading', { name: locale === 'en' ? 'Champion' : 'Nhà vô địch' }))
				.not.toBeInTheDocument();
		}
	);

	it.each(['en', 'vi'] as const)(
		'shows threshold W/L and status without irrelevant point columns in %s',
		async (locale) => {
			overwriteGetLocale(() => locale);
			const value = swissCompetition(true);
			// Even malformed legacy champion state must not turn qualification into a title.
			value.stages[0].champion = value.stages[0].entries[0];
			value.stages[0].completed_without_champion = true;
			const { container } = render(BracketPage, { data: data(value) } as never);
			await expect.element(page.getByRole('table')).toBeVisible();
			for (const label of locale === 'en'
				? ['Qualified', 'Eliminated', 'Active']
				: ['Đã đi tiếp', 'Bị loại', 'Đang thi đấu'])
				await expect.element(page.getByText(label, { exact: true }).first()).toBeVisible();
			expect(container.textContent).toContain(
				locale === 'en'
					? 'Qualify at 2 wins; eliminated at 2 losses.'
					: 'Đi tiếp khi đạt 2 trận thắng; bị loại khi thua 2 trận.'
			);
			expect(container.querySelectorAll('thead th')).toHaveLength(6);
			expect(container.querySelector('thead')?.textContent).not.toContain(
				locale === 'en' ? 'Points' : 'Điểm'
			);
			expect(
				Array.from(container.querySelectorAll('table tbody tr:first-child td'))
					.slice(1, 3)
					.map((cell) => cell.textContent?.trim())
			).toEqual(['2', '0']);
			expect(container.textContent).not.toContain('Top 0');
			await expect
				.element(page.getByRole('heading', { name: locale === 'en' ? 'Champion' : 'Nhà vô địch' }))
				.not.toBeInTheDocument();
		}
	);

	it('shows resolved Swiss qualification as completion without a champion', async () => {
		const value = swissCompetition(true);
		const stage = value.stages[0];
		stage.status = 'COMPLETE';
		stage.completed_without_champion = true;
		stage.qualification!.state = 'RESOLVED';
		stage.qualification!.qualifiers = [stage.entries[0], stage.entries[2]];
		stage.swiss_standings[2].status = 'QUALIFIED';
		render(BracketPage, { data: data(value) } as never);
		await expect
			.element(page.getByText('Swiss qualification complete', { exact: true }))
			.toBeVisible();
		await expect
			.element(page.getByText('Qualification resolved', { exact: true }).first())
			.toBeVisible();
		await expect.element(page.getByRole('heading', { name: 'Champion' })).not.toBeInTheDocument();
	});

	it('resets dependent round filters across stages and retires stale round selections on refresh', async () => {
		const value = swissCompetition();
		const nextSwiss = structuredClone(value.stages[0]);
		nextSwiss.id = 23;
		nextSwiss.sequence = 2;
		nextSwiss.name = 'Second Swiss';
		nextSwiss.rounds = nextSwiss.rounds.slice(0, 1);
		nextSwiss.rounds[0].id = 13;
		nextSwiss.rounds[0].matches.forEach((match, index) => {
			match.id = 31 + index;
			match.code = `Second Swiss-M${index + 1}`;
		});
		value.stages.splice(1, 0, nextSwiss);
		value.stages[2].sequence = 3;
		const props = {
			params: { slug: 'summer', gameId: '9' },
			data: { ...data(value), selectedStageId: 2 }
		};
		const { container, rerender } = render(BracketPage, props);
		await expect
			.element(page.getByRole('combobox', { name: 'Round', exact: true }))
			.toHaveValue('6');
		await page.getByRole('combobox', { name: 'Stage', exact: true }).selectOptions('23');
		await expect
			.element(page.getByRole('combobox', { name: 'Round', exact: true }))
			.toHaveValue('13');
		await page.getByRole('combobox', { name: 'Stage', exact: true }).selectOptions('2');
		await expect
			.element(page.getByRole('combobox', { name: 'Round', exact: true }))
			.toHaveValue('6');
		value.stages[0].rounds = value.stages[0].rounds.slice(0, 1);
		await rerender({ ...props, data: { ...data(structuredClone(value)), selectedStageId: 2 } });
		await expect
			.element(page.getByRole('combobox', { name: 'Round', exact: true }))
			.toHaveValue('3');
		expect(container.querySelector('article h3')?.textContent).toContain('Swiss qualification-M1');
	});

	it.each(['en', 'vi'] as const)(
		'uses safe publication and retirement metadata for Changes and historical links in %s',
		async (locale) => {
			overwriteGetLocale(() => locale);
			const value = swissCompetition();
			const log: PublicCompetitionChangesPage = {
				...structuredClone(changes),
				results: [
					{
						revision: 9,
						created_at: '2026-09-25T10:00:00Z',
						kind: 'swiss_round_published',
						stage_id: 2,
						round_id: 6,
						round_number: 2,
						match_ids: [7],
						rematch_count: 1,
						repeated_bye: true,
						automatic_results: []
					},
					{
						revision: 8,
						created_at: '2026-09-25T09:00:00Z',
						kind: 'result_corrected',
						stage_id: 2,
						match_id: 4,
						match_code: 'Swiss qualification-M1',
						swiss_impact: { retired_round_ids: [6], retired_match_ids: [7, 8] },
						reset_matches: [
							{
								match_id: 7,
								match_code: 'Swiss qualification-M3',
								status: 'FINAL',
								outcome: 'PLAYED',
								side_one: 'Blue Team',
								side_two: 'Green Team',
								side_one_score: 2,
								side_two_score: 0,
								winner: 'Blue Team',
								applied_series_length: 3,
								started_at: null,
								completed_at: '2026-09-25T08:00:00Z'
							}
						]
					},
					{
						revision: 1,
						created_at: '2026-09-25T01:00:00Z',
						kind: 'draw_published',
						stage_id: 2,
						draw_id: 1,
						round_id: 3,
						round_number: 1,
						match_ids: [4, 5],
						rematch_count: 0,
						repeated_bye: false,
						automatic_results: [
							{
								match_id: 5,
								match_code: 'Swiss qualification-M2',
								status: 'FINAL',
								outcome: 'BYE',
								side_one: 'Green Team',
								side_two: null,
								side_one_score: null,
								side_two_score: null,
								winner: 'Green Team',
								applied_series_length: null,
								started_at: null,
								completed_at: null
							}
						]
					}
				]
			};
			const stage = value.stages[0];
			stage.draw_state = 'AWAITING_REPLACEMENT';
			stage.rounds = [];
			stage.entries = [];
			stage.swiss_standings = [];
			stage.swiss_rules!.round_limit = null;
			stage.qualification!.state = 'PROVISIONAL';
			stage.qualification!.cutoff_ties = [];
			const { container } = render(BracketPage, {
				data: { ...data(value), changes: log, selectedStageId: 2 }
			} as never);
			await expect
				.element(
					page.getByText(
						locale === 'en' ? 'Awaiting replacement draw' : 'Đang chờ nhánh đấu thay thế',
						{ exact: true }
					)
				)
				.toBeVisible();
			expect(container.textContent).toContain(
				locale === 'en' ? 'Swiss round 2 published' : 'Đã công bố vòng Swiss 2'
			);
			expect(container.textContent).toContain(
				locale === 'en' ? 'Required rematches: 1.' : 'Vòng đã công bố này có 1 cặp tái đấu.'
			);
			expect(container.textContent).toContain(
				locale === 'en'
					? 'A repeat bye was needed in this published round.'
					: 'Vòng đã công bố này cần miễn đấu lặp lại.'
			);
			expect(container.textContent).toContain(
				locale === 'en'
					? 'Rounds moved to history: 1; recorded results are preserved.'
					: '1 vòng đấu đã được lưu vào lịch sử; kết quả được giữ nguyên.'
			);
			const historicalLabel =
				locale === 'en'
					? 'Historical match Swiss qualification-M3'
					: 'Trận lịch sử Swiss qualification-M3';
			await expect
				.element(page.getByRole('link', { name: historicalLabel, exact: true }))
				.toHaveAttribute('href', '#change-8-match-7');
			await expect
				.element(
					page.getByRole('link', {
						name: locale === 'en' ? 'Historical match #8' : 'Trận lịch sử #8',
						exact: true
					})
				)
				.toHaveAttribute('href', '#change-8');
			expect(container.querySelector('#change-8-match-7')?.textContent).toContain('2–0');
			expect(container.querySelector('#change-1-match-5')?.textContent).toContain(
				locale === 'en' ? 'Bye' : 'Miễn đấu'
			);
			expect(container.querySelector('#change-1-match-5')?.textContent).not.toMatch(/\b0–0\b/);
			expect(container.textContent).not.toContain('OPPONENT_POINTS');
			expect(container.textContent).not.toContain('fingerprint');
			expect(container.querySelector('#round-select')).toBeNull();
			expect(container.textContent).not.toContain(
				locale === 'en' ? 'Current round:' : 'Vòng hiện tại:'
			);
		}
	);
});

it.each(['en', 'vi'] as const)(
	'shows lifecycle availability and frozen historical contests in %s',
	async (locale) => {
		overwriteGetLocale(() => locale);
		const ended = structuredClone(competition);
		ended.ending = { stage_id: 2, ended_at: '2026-10-26T00:00:00Z', champion: null };
		ended.stages[0].lifecycle_state = 'CLOSED';
		ended.stages[0].rounds[0].matches[0].slots[0].entry!.status = 'WITHDRAWN';
		const rendered = render(BracketPage, { data: data(ended) } as never);
		await expect
			.element(page.getByText(locale === 'en' ? 'Competition ended' : 'Giải đấu đã kết thúc'))
			.toBeVisible();
		expect(rendered.container.textContent).toContain(locale === 'en' ? 'Withdrawn' : 'Đã rút lui');
		expect(rendered.container.textContent).toContain(
			locale === 'en' ? 'Source contests are frozen.' : 'Các trận tại vòng nguồn đã được đóng băng.'
		);
	}
);

it.each(['en', 'vi'] as const)(
	'keeps retired stages and reopening Changes readable in %s',
	async (locale) => {
		overwriteGetLocale(() => locale);
		const retired = structuredClone(competition);
		retired.stages[0].lifecycle_state = 'RETIRED';
		retired.stages[0].draw_state = 'AWAITING_REPLACEMENT';
		retired.stages[0].rounds[0].matches[0].historical = true;
		retired.stages[0].rounds[0].matches[0].code = 'M1';
		const props = data(retired);
		props.changes = {
			...props.changes,
			results: [
				{
					revision: 9,
					created_at: '2026-10-26T00:00:00Z',
					kind: 'competition_reopened',
					retired_draws: [7],
					reset_matches: [
						{
							match_id: 4,
							match_code: 'M1',
							status: 'FINAL',
							outcome: 'PLAYED',
							side_one: 'Blue Team',
							side_two: 'Red Team',
							side_one_score: 2,
							side_two_score: 1,
							winner: 'Blue Team',
							applied_series_length: 3,
							applied_series_mode: 'BEST_OF',
							started_at: null,
							completed_at: null
						}
					]
				}
			]
		};
		const rendered = render(BracketPage, { data: props } as never);
		expect(rendered.container.textContent).toContain(
			locale === 'en' ? 'Retired' : 'Đã lưu lịch sử'
		);
		await expect
			.element(page.getByText(locale === 'en' ? 'Competition reopened' : 'Giải đấu đã mở lại'))
			.toBeVisible();
		expect(rendered.container.querySelector('#change-9-match-4')?.textContent).toContain('M1');
		expect(rendered.container.querySelector('#change-9-match-4')?.textContent).toContain('2');
	}
);
