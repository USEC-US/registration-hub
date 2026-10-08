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
			id: 21,
			number: 1,
			section: 'UPPER',
			series_length_override: null,
			matches: [match(31, 'U1', 'PENDING')]
		},
		{
			id: 22,
			number: 1,
			section: 'LOWER',
			series_length_override: null,
			matches: [match(32, 'L1', 'PENDING', 31, 'LOSER')]
		},
		{
			id: 23,
			number: 1,
			section: 'FINALS',
			series_length_override: null,
			matches: [match(33, 'F1', 'PENDING', 31, 'WINNER')]
		},
		{
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
		await expect.element(page.getByText('Match R1M1 result corrected')).toBeVisible();
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
			await expect.element(page.getByText('Loser of U1').last()).toBeVisible();
			await expect.element(page.getByText('Winner of U1').last()).toBeVisible();
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

	it.each(['en', 'vi'] as const)('renders retained correction snapshots in %s', async (locale) => {
		overwriteGetLocale(() => locale);
		const correctionChanges = structuredClone(changes);
		correctionChanges.results[0] = {
			...correctionChanges.results[0],
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
		await expect.element(page.getByText('Đã sửa kết quả trận R1M1')).toBeVisible();
	});
});
