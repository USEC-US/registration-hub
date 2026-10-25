from collections import Counter
from decimal import Decimal

from django.test import SimpleTestCase

from competitions.round_robin import (
    RoundRobinResult,
    allocate_snake_groups,
    generate_round_robin,
    rank_group,
)


class RoundRobinTests(SimpleTestCase):
    def test_circle_pair_counts_and_reversed_second_cycle(self):
        for size, single_count in ((3, 3), (4, 6), (5, 10), (16, 120)):
            for meetings in (1, 2):
                with self.subTest(size=size, meetings=meetings):
                    rounds = generate_round_robin(
                        tuple(range(1, size + 1)), meetings=meetings
                    )
                    pairs = [pair for round_ in rounds for pair in round_.pairings]
                    self.assertEqual(len(pairs), single_count * meetings)
                    self.assertEqual(
                        set(Counter(tuple(sorted(pair)) for pair in pairs).values()),
                        {meetings},
                    )
                    for round_ in rounds:
                        ids = [entry for pair in round_.pairings for entry in pair]
                        self.assertEqual(len(ids), len(set(ids)))
                    if meetings == 2:
                        half = len(rounds) // 2
                        for first, second in zip(
                            rounds[:half], rounds[half:], strict=True
                        ):
                            self.assertEqual(
                                second.pairings,
                                tuple((b, a) for a, b in first.pairings),
                            )

    def test_odd_group_rest_has_no_match(self):
        rounds = generate_round_robin((10, 20, 30), meetings=1)
        self.assertEqual(
            Counter(round_.resting_entry_id for round_ in rounds), {10: 1, 20: 1, 30: 1}
        )
        self.assertTrue(all(len(round_.pairings) == 1 for round_ in rounds))
        for round_ in rounds:
            self.assertNotIn(round_.resting_entry_id, round_.pairings[0])

    def test_snake_allocation(self):
        self.assertEqual(
            allocate_snake_groups(tuple(range(1, 9)), 2), ((1, 4, 5, 8), (2, 3, 6, 7))
        )
        self.assertEqual(
            tuple(map(len, allocate_snake_groups(tuple(range(1, 8)), 3))), (3, 2, 2)
        )

    def test_invalid_fields_and_meetings(self):
        for ids, meetings in (
            ((1,), 1),
            ((1, 1), 1),
            ((1, 2), 3),
            (tuple(range(257)), 1),
        ):
            with (
                self.subTest(ids=ids, meetings=meetings),
                self.assertRaises(ValueError),
            ):
                generate_round_robin(ids, meetings=meetings)
        with self.assertRaises(ValueError):
            allocate_snake_groups((1, 2, 3), 2)

    def test_draw_forfeit_and_double_forfeit_metrics(self):
        results = (
            RoundRobinResult(1, 1, 2, "PLAYED", 1, 1, None),
            RoundRobinResult(2, 1, 3, "FORFEIT", 1, 0, 1),
            RoundRobinResult(3, 2, 3, "DOUBLE_FORFEIT", 0, 1, None),
        )
        rows = rank_group(
            (1, 2, 3),
            results,
            points=(Decimal("3"), Decimal("1"), Decimal("0")),
            tiebreaks=(),
        )
        self.assertEqual(
            [
                (row.entry_id, row.points, row.wins, row.draws, row.losses)
                for row in rows
            ],
            [
                (1, Decimal("4"), 1, 1, 0),
                (2, Decimal("1"), 0, 1, 1),
                (3, Decimal("0"), 0, 0, 2),
            ],
        )
        self.assertEqual([row.games_won for row in rows], [1, 1, 0])
        self.assertEqual([row.game_difference for row in rows], [0, 0, 0])
        self.assertEqual([row.played for row in rows], [2, 2, 2])
        decimal_rows = rank_group(
            (1, 2, 3),
            results,
            points=(Decimal("2.50"), Decimal("0.75"), Decimal("0.25")),
            tiebreaks=(),
        )
        self.assertEqual(
            [row.points for row in decimal_rows],
            [Decimal("3.25"), Decimal("0.75"), Decimal("0.25")],
        )

    def test_head_to_head_does_not_restart_after_subgroup_separates(self):
        games = (
            (1, 2, 2, 1),
            (1, 2, 1, 1),
            (1, 3, 2, 1),
            (1, 3, 0, 2),
            (2, 3, 2, 0),
            (2, 3, 2, 0),
            (3, 4, 2, 0),
            (3, 4, 1, 1),
        )
        results = tuple(
            RoundRobinResult(
                index, a, b, "PLAYED", x, y, a if x > y else b if y > x else None
            )
            for index, (a, b, x, y) in enumerate(games, 1)
        )
        rows = rank_group(
            (1, 2, 3, 4),
            results,
            points=(Decimal("3"), Decimal("1"), Decimal("0")),
            tiebreaks=("HEAD_TO_HEAD", "GAME_DIFFERENCE"),
        )
        self.assertEqual(
            [(row.entry_id, row.rank) for row in rows], [(2, 1), (1, 2), (3, 3), (4, 4)]
        )

    def test_equal_ranks_do_not_use_seed_to_break_cutoff_tie(self):
        rows = rank_group(
            (30, 10, 20),
            (),
            points=(Decimal("3"), Decimal("1"), Decimal("0")),
            tiebreaks=("HEAD_TO_HEAD", "GAME_DIFFERENCE", "GAMES_WON"),
        )
        self.assertEqual(
            [(row.entry_id, row.rank) for row in rows], [(30, 1), (10, 1), (20, 1)]
        )

    def test_unknown_or_duplicate_criteria_are_rejected(self):
        for criteria in (("UNKNOWN",), ("MATCH_WINS", "MATCH_WINS")):
            with self.subTest(criteria=criteria), self.assertRaises(ValueError):
                rank_group(
                    (1, 2),
                    (),
                    points=(Decimal("3"), Decimal("1"), Decimal("0")),
                    tiebreaks=criteria,
                )
