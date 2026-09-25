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
									entry: { id: 11, seed: 1, display_name: 'Blue Team', display_tag: 'BLUE' }
								},
								{
									position: 2,
									is_resolved: true,
									is_empty: false,
									source_match_id: null,
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

	it('renders the bracket in Vietnamese', async () => {
		overwriteGetLocale(() => 'vi');
		render(BracketPage, { data: data() } as never);

		await expect.element(page.getByRole('heading', { name: 'Valorant · Nhánh đấu' })).toBeVisible();
		await expect.element(page.getByText('Đang diễn ra', { exact: true })).toBeVisible();
		await expect.element(page.getByText('Đã sửa kết quả trận R1M1')).toBeVisible();
	});
});
