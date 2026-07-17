import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import type { PublicTournament } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import HomePage from './+page.svelte';
import TournamentListPage from './tournaments/+page.svelte';
import TournamentDetailPage from './tournaments/[slug]/+page.svelte';

const tournament: PublicTournament = {
	id: 1,
	name: 'USEC Summer 2026',
	slug: 'usec-summer-2026',
	description: 'A university tournament for HCMUS students.',
	starts_at: '2026-08-15T01:00:00Z',
	ends_at: '2026-08-17T10:00:00Z',
	location: 'HCMUS',
	tournament_games: [
		{
			id: 9,
			game_name: 'Valorant',
			game_slug: 'valorant',
			team_size_min: 5,
			team_size_max: 5,
			registration_opens_at: '2026-07-20T01:00:00Z',
			registration_closes_at: '2026-08-10T10:00:00Z',
			registration_capacity: 32,
			capacity_remaining: 12,
			fee_amount: '50000.00',
			fee_currency: 'VND',
			registration_state: 'open',
			is_registration_open: true
		}
	]
};

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('public tournament pages', () => {
	it('renders the localized home chrome and real tournament data', async () => {
		render(HomePage, { data: { tournaments: [tournament] }, params: {} });

		await expect
			.element(page.getByRole('heading', { level: 1, name: 'USEC Tournament Registration Hub' }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('heading', { level: 3, name: tournament.name }))
			.toBeInTheDocument();
		expect(document.title).toBe('USEC Tournament Registration Hub');
	});

	it('renders a localized empty state without fabricated tournament cards', async () => {
		overwriteGetLocale(() => 'vi');
		render(HomePage, { data: { tournaments: [] }, params: {} });

		await expect
			.element(page.getByText('Hiện không có giải đấu nào được công bố.'))
			.toBeInTheDocument();
		expect(page.getByRole('article').elements()).toHaveLength(0);
	});

	it('renders the direct tournament index heading and semantic card hierarchy', async () => {
		render(TournamentListPage, { data: { tournaments: [tournament] }, params: {} });

		await expect
			.element(page.getByRole('heading', { level: 1, name: 'Published tournaments' }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('heading', { level: 2, name: tournament.name }))
			.toBeInTheDocument();
	});

	it('renders tournament metadata, configured games, and an open registration action', async () => {
		const { container } = render(TournamentDetailPage, {
			data: { tournament },
			params: { slug: tournament.slug }
		});

		await expect
			.element(page.getByRole('heading', { level: 1, name: tournament.name }))
			.toBeInTheDocument();
		await expect.element(page.getByText(tournament.description)).toBeInTheDocument();
		await expect
			.element(page.getByRole('heading', { level: 2, name: 'Configured games' }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('heading', { level: 3, name: 'Valorant' }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('link', { name: 'Register' }))
			.toHaveAttribute('href', '/tournaments/usec-summer-2026/games/9/register');
		expect(container.querySelectorAll('time[datetime]')).toHaveLength(2);
		expect(document.title).toBe(`${tournament.name} · USEC Tournament Registration Hub`);
	});

	it('shows a localized empty game state and no registration action', async () => {
		overwriteGetLocale(() => 'vi');
		render(TournamentDetailPage, {
			data: { tournament: { ...tournament, tournament_games: [] } },
			params: { slug: tournament.slug }
		});

		await expect
			.element(page.getByText('Giải đấu này chưa có nội dung thi đấu.'))
			.toBeInTheDocument();
		expect(page.getByRole('link', { name: 'Đăng ký' }).elements()).toHaveLength(0);
	});
});
