import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import type { PublicTournament } from '$lib/api/types';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { resolveDisplayTimeZone } from '$lib/time/tournament-time';
import HomePage from './+page.svelte';
import TournamentListPage from './tournaments/+page.svelte';
import TournamentDetailPage from './tournaments/[slug]/+page.svelte';

const tournament: PublicTournament = {
	id: 1,
	name: 'USEC Summer 2026',
	slug: 'usec-summer-2026',
	description: 'A university tournament for HCMUS students.',
	cover_image: null,
	starts_at: '2026-08-15T01:00:00Z',
	ends_at: '2026-08-17T10:00:00Z',
	location: 'HCMUS',
	is_featured: false,
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

const displayTimeZone = resolveDisplayTimeZone('Asia/Ho_Chi_Minh');

function makeTournament(overrides: Partial<PublicTournament>): PublicTournament {
	return {
		...tournament,
		id: overrides.id ?? tournament.id,
		name: overrides.name ?? tournament.name,
		slug: overrides.slug ?? tournament.slug,
		description: overrides.description ?? tournament.description,
		cover_image: overrides.cover_image ?? tournament.cover_image,
		starts_at: overrides.starts_at ?? tournament.starts_at,
		ends_at: overrides.ends_at ?? tournament.ends_at,
		location: overrides.location ?? tournament.location,
		is_featured: overrides.is_featured ?? tournament.is_featured,
		tournament_games: overrides.tournament_games ?? tournament.tournament_games
	};
}

beforeEach(() => {
	overwriteGetLocale(() => 'en');
});

afterEach(() => {
	overwriteGetLocale(() => 'en');
});

describe('public tournament pages', () => {
	it('renders the localized home chrome and real tournament data', async () => {
		render(HomePage, { data: { tournaments: [tournament], displayTimeZone }, params: {} });

		await expect
			.element(page.getByRole('heading', { level: 1, name: 'Tournament Registration Portal' }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('heading', { level: 3, name: tournament.name }))
			.toBeInTheDocument();
		expect(document.title).toBe('University of Science Esports Club');
	});

	it('renders a three-tournament home preview with a link to the full catalogue', async () => {
		const tournaments = [
			makeTournament({ id: 1, name: 'Featured Cup', slug: 'featured-cup', is_featured: true }),
			makeTournament({ id: 2, name: 'Campus Clash', slug: 'campus-clash' }),
			makeTournament({ id: 3, name: 'Spring Arena', slug: 'spring-arena' }),
			makeTournament({ id: 4, name: 'Fourth Tournament', slug: 'fourth-tournament' })
		];

		const { container } = render(HomePage, { data: { tournaments, displayTimeZone }, params: {} });

		expect(container.querySelectorAll('article')).toHaveLength(3);
		await expect.element(page.getByRole('link', { name: 'Featured Cup' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Campus Clash' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Spring Arena' })).toBeVisible();
		expect(page.getByRole('link', { name: 'Fourth Tournament' }).elements()).toHaveLength(0);
		await expect
			.element(page.getByRole('link', { name: 'See all tournaments' }))
			.toHaveAttribute('href', '/en/tournaments');
	});

	it('renders a localized empty state without fabricated tournament cards', async () => {
		overwriteGetLocale(() => 'vi');
		render(HomePage, { data: { tournaments: [], displayTimeZone }, params: {} });

		await expect
			.element(page.getByText('Hiện không có giải đấu nào được công bố.'))
			.toBeInTheDocument();
		expect(page.getByRole('article').elements()).toHaveLength(0);
	});

	it('renders the direct tournament index heading and semantic card hierarchy', async () => {
		render(TournamentListPage, {
			data: { tournaments: [tournament], displayTimeZone },
			params: {}
		});

		await expect
			.element(page.getByRole('heading', { level: 1, name: 'Published tournaments' }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('heading', { level: 2, name: tournament.name }))
			.toBeInTheDocument();
	});

	it('renders all published tournaments in a responsive listing grid once each', () => {
		const tournaments = [
			makeTournament({ id: 1, name: 'Featured Cup', slug: 'featured-cup', is_featured: true }),
			makeTournament({ id: 2, name: 'Campus Clash', slug: 'campus-clash' }),
			makeTournament({ id: 3, name: 'Spring Arena', slug: 'spring-arena' })
		];

		const { container } = render(TournamentListPage, {
			data: { tournaments, displayTimeZone },
			params: {}
		});
		const listing = container.querySelector('section[aria-label="Published tournaments"]');

		expect(listing).toHaveClass('grid', 'grid-cols-1', 'md:grid-cols-2', 'xl:grid-cols-3');
		expect(container.querySelectorAll('article')).toHaveLength(3);
		for (const item of tournaments) {
			expect(page.getByRole('link', { name: item.name }).elements()).toHaveLength(1);
		}
	});

	it('uses the full bottom metadata row for the longer Dates datum', () => {
		const { container } = render(TournamentListPage, {
			data: { tournaments: [tournament], displayTimeZone },
			params: {}
		});
		const datesTerm = [...container.querySelectorAll('dt')].find(
			(element) => element.textContent === 'Dates'
		);

		expect(datesTerm?.parentElement).toHaveClass('col-span-2');
	});
	it('keeps explanatory tournament-list prose in the body typeface', () => {
		const { container } = render(TournamentListPage, {
			data: { tournaments: [tournament], displayTimeZone },
			params: {}
		});
		const note = [...container.querySelectorAll('p')].find((element) =>
			element.textContent?.includes('Availability, fees, and registration windows')
		);

		expect(note).toBeDefined();
		expect(note).not.toHaveClass('font-mono-data');
	});
	it('describes a blank tournament location as unannounced instead of online', async () => {
		overwriteGetLocale(() => 'vi');
		const tournamentWithoutLocation = { ...tournament, location: '' };

		render(TournamentListPage, {
			data: { tournaments: [tournamentWithoutLocation], displayTimeZone },
			params: {}
		});
		render(TournamentDetailPage, {
			data: { tournament: tournamentWithoutLocation, displayTimeZone },
			params: { slug: tournament.slug }
		});

		expect(page.getByText('Địa điểm sẽ được cập nhật').elements()).toHaveLength(2);
		expect(page.getByText('Trực tuyến').elements()).toHaveLength(0);
	});
	it('keeps UTC values in semantic times and formats them in the merged display zone', () => {
		const boundaryTournament = {
			...tournament,
			starts_at: '2026-08-15T01:00:00Z',
			ends_at: '2026-08-15T02:00:00Z',
			tournament_games: [
				{
					...tournament.tournament_games[0],
					registration_opens_at: '2026-08-15T03:00:00Z',
					registration_closes_at: '2026-08-15T04:00:00Z'
				}
			]
		};
		const viewerTimeZone = resolveDisplayTimeZone('America/New_York');

		const card = render(TournamentListPage, {
			data: { tournaments: [boundaryTournament], displayTimeZone: viewerTimeZone },
			params: {}
		});
		const cardTimes = [...card.container.querySelectorAll('time')];
		expect(cardTimes.map((element) => element.dateTime)).toEqual([
			boundaryTournament.starts_at,
			boundaryTournament.ends_at
		]);
		expect(cardTimes[0]).toHaveTextContent('Aug 14, 2026');

		const detail = render(TournamentDetailPage, {
			data: { tournament: boundaryTournament, displayTimeZone: viewerTimeZone },
			params: { slug: boundaryTournament.slug }
		});
		const detailTimes = [...detail.container.querySelectorAll('time')];
		expect(detailTimes.map((element) => element.dateTime)).toEqual([
			boundaryTournament.starts_at,
			boundaryTournament.ends_at,
			boundaryTournament.tournament_games[0].registration_opens_at,
			boundaryTournament.tournament_games[0].registration_closes_at
		]);
		expect(detailTimes[0]).toHaveTextContent('Aug 14, 2026, 9:00 PM EDT');
		expect(detailTimes[2]).toHaveTextContent('Aug 14, 2026, 11:00 PM EDT');
	});
	it('renders tournament metadata, configured games, and an open registration action', async () => {
		const { container } = render(TournamentDetailPage, {
			data: { tournament, displayTimeZone },
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
			.toHaveAttribute('href', '/en/tournaments/usec-summer-2026/games/9/register');
		expect(container.querySelectorAll('time[datetime]')).toHaveLength(4);
		expect(document.title).toBe(`${tournament.name} · University of Science Esports Club`);
	});

	it('keeps configured not-open, full, and closed games visible without Register links', async () => {
		const unavailableGames = (
			[
				['not_open', 'Upcoming game'],
				['full', 'Full game'],
				['closed', 'Closed game']
			] as const
		).map(([registration_state, game_name], index) => ({
			...tournament.tournament_games[0],
			id: 20 + index,
			game_name,
			game_slug: `game-${index}`,
			registration_state,
			is_registration_open: false
		}));

		render(TournamentDetailPage, {
			data: {
				tournament: { ...tournament, tournament_games: unavailableGames },
				displayTimeZone
			},
			params: { slug: tournament.slug }
		});

		for (const game of unavailableGames) {
			await expect
				.element(page.getByRole('heading', { level: 3, name: game.game_name }))
				.toBeInTheDocument();
		}
		expect(page.getByRole('link', { name: 'Register' }).elements()).toHaveLength(0);
		expect(page.getByText('Not open', { exact: true }).elements()).toHaveLength(2);
		expect(page.getByText('Full', { exact: true }).elements()).toHaveLength(2);
		expect(page.getByText('Closed', { exact: true }).elements()).toHaveLength(2);
	});
	it('shows a localized empty game state and no registration action', async () => {
		overwriteGetLocale(() => 'vi');
		render(TournamentDetailPage, {
			data: { tournament: { ...tournament, tournament_games: [] }, displayTimeZone },
			params: { slug: tournament.slug }
		});

		await expect
			.element(page.getByText('Giải đấu này chưa có nội dung thi đấu.'))
			.toBeInTheDocument();
		expect(page.getByRole('link', { name: 'Đăng ký' }).elements()).toHaveLength(0);
	});
});
