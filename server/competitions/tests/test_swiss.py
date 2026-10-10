import itertools
import json
import os
import random
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal

from django.test import SimpleTestCase

from competitions.swiss import (
    SwissPairingError,
    SwissResult,
    pair_swiss_round,
    rank_swiss,
    resolve_round_limit,
)

FIXED = "SWISS_FIXED"
THRESHOLD = "SWISS_THRESHOLD"
POINTS = (Decimal("3"), Decimal("1"), Decimal("0"))
RULES = ("OPPONENT_POINTS", "GAME_DIFFERENCE", "GAMES_WON")


def standings(
    seeds, results=(), *, format=FIXED, points=POINTS, tiebreaks=RULES, **kwargs
):
    return rank_swiss(
        seeds, results, format=format, points=points, tiebreaks=tiebreaks, **kwargs
    )


def history(edges):
    return [
        SwissResult(i, i, a, b, "FORFEIT", winner_id=a)
        for i, (a, b) in enumerate(edges, 1)
    ]


def matchings(ids):
    """Tiny reference only: enumerate perfect matchings without solver costs."""
    if not ids:
        yield ()
        return
    first = ids[0]
    for i, other in enumerate(ids[1:], 1):
        for remaining in matchings(ids[1:i] + ids[i + 1 :]):
            yield ((first, other),) + remaining


def objective(pairs, bye, seeds, rows, previous, format):
    by_id = {r.entry_id: r for r in rows}

    def group(i):
        return (
            (by_id[i].points,) if format == FIXED else (by_id[i].wins, -by_id[i].losses)
        )

    active = [r.entry_id for r in rows if r.status == "ACTIVE" and r.entry_id != bye]
    groups = {
        key: sorted((i for i in active if group(i) == key), key=seeds.get)
        for key in {group(i) for i in active}
    }
    fairness = () if bye is None else (by_id[bye].bye_count, *group(bye), -seeds[bye])
    repeats = cross = folding = 0
    distance = Decimal(0)
    for a, b in pairs:
        repeats += frozenset((a, b)) in previous
        cross += group(a) != group(b)
        if format == FIXED:
            distance += abs(by_id[a].points - by_id[b].points)
        else:
            distance += abs(by_id[a].wins - by_id[b].wins) + abs(
                by_id[a].losses - by_id[b].losses
            )
        members = sorted(set(groups[group(a)] + groups[group(b)]), key=seeds.get)
        folding += abs(members.index(a) + members.index(b) - (len(members) - 1))
    return fairness, repeats, cross, distance, folding


class SwissBoundsTests(SimpleTestCase):
    def test_round_limits_and_saved_seed_folding(self):
        for n, automatic, cap in (
            (2, 1, 1),
            (3, 2, 3),
            (8, 3, 7),
            (9, 4, 9),
            (256, 8, 64),
        ):
            self.assertEqual(
                resolve_round_limit(
                    n, format=FIXED, round_count=None, win_target=None, loss_limit=None
                ),
                automatic,
            )
            self.assertEqual(
                resolve_round_limit(
                    n, format=FIXED, round_count=cap, win_target=None, loss_limit=None
                ),
                cap,
            )
            with self.assertRaises(ValueError):
                resolve_round_limit(
                    n,
                    format=FIXED,
                    round_count=cap + 1,
                    win_target=None,
                    loss_limit=None,
                )
        seeds = dict(zip((80, 70, 60, 50, 40, 30, 20, 10), range(1, 9)))
        pairing = pair_swiss_round(seeds, standings(seeds), (), format=FIXED)
        self.assertEqual(pairing.pairs, ((80, 10), (70, 20), (60, 30), (50, 40)))
        seeds = {i: i for i in range(1, 9)}
        self.assertEqual(
            pair_swiss_round(seeds, standings(seeds), (), format=FIXED).pairs,
            ((1, 8), (2, 7), (3, 6), (4, 5)),
        )

    def test_threshold_sum_and_boolean_bounds(self):
        for n, w, loss, limit in (
            (2, 1, 1, 1),
            (3, 2, 2, 3),
            (8, 4, 4, 7),
            (9, 5, 5, 9),
            (256, 33, 32, 64),
        ):
            self.assertEqual(
                resolve_round_limit(
                    n, format=THRESHOLD, round_count=None, win_target=w, loss_limit=loss
                ),
                limit,
            )
            with self.assertRaises(ValueError):
                resolve_round_limit(
                    n,
                    format=THRESHOLD,
                    round_count=None,
                    win_target=w + 1,
                    loss_limit=loss,
                )
        for kwargs in (
            {"entrant_count": True},
            {"entrant_count": 1},
            {"entrant_count": 257},
            {"round_count": True},
            {"round_count": 0},
            {"round_count": 1.0},
            {"win_target": 1},
            {"format": "ROUND_ROBIN"},
        ):
            values = dict(
                entrant_count=8,
                format=FIXED,
                round_count=None,
                win_target=None,
                loss_limit=None,
            )
            values.update(kwargs)
            with self.assertRaises(ValueError):
                resolve_round_limit(**values)
        for w, loss in ((True, 2), (2, False), (0, 2), (None, 2), (2, None)):
            with self.assertRaises(ValueError):
                resolve_round_limit(
                    8, format=THRESHOLD, round_count=None, win_target=w, loss_limit=loss
                )
        with self.assertRaises(ValueError):
            resolve_round_limit(
                8, format=THRESHOLD, round_count=3, win_target=2, loss_limit=2
            )


class SwissStandingsTests(SimpleTestCase):
    def test_exact_points_games_and_repeated_forfeit_opponents(self):
        seeds = {1: 3, 2: 1, 3: 2}
        results = [
            SwissResult(1, 1, 1, 2, "PLAYED", 2, 1, 1),
            SwissResult(2, 2, 1, 2, "FORFEIT", winner_id=2),
            SwissResult(3, 3, 2, 3, "PLAYED", 2, 2),
            SwissResult(4, 4, 3, None, "BYE", winner_id=3),
        ]
        rows = {r.entry_id: r for r in standings(seeds, results)}
        self.assertEqual(
            (
                rows[1].played,
                rows[1].wins,
                rows[1].draws,
                rows[1].losses,
                rows[1].points,
                rows[1].games_won,
                rows[1].game_difference,
                rows[1].opponent_points,
                rows[1].bye_count,
            ),
            (2, 1, 0, 1, Decimal(3), 2, 1, Decimal(8), 0),
        )
        self.assertEqual(
            (rows[2].points, rows[2].opponent_points, rows[2].games_won),
            (Decimal(4), Decimal(10), 3),
        )
        self.assertEqual(
            (
                rows[3].played,
                rows[3].points,
                rows[3].opponent_points,
                rows[3].bye_count,
            ),
            (2, Decimal(4), Decimal(4), 1),
        )
        self.assertTrue(all(r.status == "ACTIVE" for r in rows.values()))

    def test_double_forfeit_and_qualifying_bye(self):
        seeds = {i: i for i in range(1, 6)}
        results = [
            SwissResult(1, 1, 1, 2, "FORFEIT", winner_id=1),
            SwissResult(2, 2, 1, 3, "FORFEIT", winner_id=1),
            SwissResult(3, 3, 1, None, "BYE", winner_id=1),
            SwissResult(4, 3, 2, 3, "DOUBLE_FORFEIT"),
        ]
        rows = {
            r.entry_id: r
            for r in standings(
                seeds, results, format=THRESHOLD, win_target=3, loss_limit=3
            )
        }
        bye = rows[1]
        self.assertEqual((bye.wins, bye.games_won, bye.bye_count), (3, 0, 1))
        self.assertEqual(bye.status, "QUALIFIED")
        left, right = [r for r in standings({2: 1, 3: 2}, results[-1:])]
        self.assertEqual(
            (left.losses, right.losses, left.points, right.points), (1, 1, 0, 0)
        )
        nonzero_loss = standings(
            {2: 1, 3: 2}, results[-1:], points=(Decimal(4), Decimal(2), Decimal(1))
        )
        self.assertTrue(all(r.points == 0 for r in nonzero_loss))

    def test_tied_ranks_never_use_saved_seed_as_qualification(self):
        rows = standings({1: 9, 2: 1, 3: 4})
        self.assertEqual([(r.entry_id, r.rank) for r in rows], [(2, 1), (3, 1), (1, 1)])
        results = [SwissResult(1, 1, 1, 2, "PLAYED", 1, 1)]
        rows = standings({1: 3, 2: 2, 3: 1}, results, tiebreaks=())
        self.assertEqual([(r.entry_id, r.rank) for r in rows], [(2, 1), (1, 1), (3, 3)])

    def test_tiebreak_order_and_decimal_points(self):
        seeds = {i: i for i in range(1, 5)}
        results = [
            SwissResult(1, 1, 1, 2, "PLAYED", 2, 0, 1),
            SwissResult(2, 1, 3, 4, "FORFEIT", winner_id=3),
        ]
        rows = standings(
            seeds, results, points=(Decimal("0.25"), Decimal("0.10"), Decimal("0.05"))
        )
        self.assertEqual([r.entry_id for r in rows], [1, 3, 4, 2])
        self.assertEqual(rows[0].points, Decimal("0.25"))
        self.assertEqual(rows[0].opponent_points, Decimal("0.05"))
        self.assertEqual(
            standings(seeds, results, tiebreaks=("MATCH_WINS",))[0].wins, 1
        )

    def test_threshold_exit_and_rank_record_before_points(self):
        seeds = {1: 1, 2: 2, 3: 3}
        results = [SwissResult(1, 1, 1, 2, "FORFEIT", winner_id=1)]
        rows = standings(
            seeds,
            results,
            format=THRESHOLD,
            win_target=1,
            loss_limit=1,
            points=(Decimal(0), Decimal(1), Decimal(9)),
        )
        self.assertEqual(
            [(r.entry_id, r.status) for r in rows],
            [(1, "QUALIFIED"), (3, "ACTIVE"), (2, "ELIMINATED")],
        )
        with self.assertRaises(ValueError):
            standings(
                seeds,
                results + [SwissResult(2, 2, 1, 3, "FORFEIT", winner_id=1)],
                format=THRESHOLD,
                win_target=1,
                loss_limit=2,
            )

    def test_invalid_or_incomplete_results_are_rejected(self):
        seeds = {1: 1, 2: 2, 3: 3}
        invalid = [
            SwissResult(1, 1, 1, 4, "FORFEIT", winner_id=1),
            SwissResult(1, 1, 1, 1, "FORFEIT", winner_id=1),
            SwissResult(1, 1, 1, 2, ""),
            SwissResult(1, 1, 1, 2, "EMPTY"),
            SwissResult(1, 1, 1, 2, "FORFEIT"),
            SwissResult(1, 1, 1, 2, "DOUBLE_FORFEIT", winner_id=1),
            SwissResult(1, 1, 1, None, "BYE", winner_id=2),
            SwissResult(1, 1, 1, 2, "PLAYED"),
            SwissResult(1, 1, 1, 2, "PLAYED", -1, 0, 2),
            SwissResult(1, 1, 1, 2, "PLAYED", True, 0, 1),
            SwissResult(1, 1, 1, 2, "PLAYED", 2, 1, 2),
        ]
        for result in invalid:
            with self.subTest(result=result), self.assertRaises(ValueError):
                standings(seeds, [result])
        with self.assertRaises(ValueError):
            standings(
                seeds,
                [
                    SwissResult(1, 1, 1, 2, "FORFEIT", winner_id=1),
                    SwissResult(2, 1, 1, 3, "FORFEIT", winner_id=1),
                ],
            )
        with self.assertRaises(ValueError):
            standings(
                seeds,
                [SwissResult(1, 1, 1, 2, "PLAYED", 1, 1)],
                format=THRESHOLD,
                win_target=2,
                loss_limit=2,
            )
        for rules in (("HEAD_TO_HEAD",), ("GAMES_WON", "GAMES_WON")):
            with self.assertRaises(ValueError):
                standings(seeds, tiebreaks=rules)
        for bad in ({1: 1, 2: 1}, {1: True, 2: 2}):
            with self.assertRaises(ValueError):
                standings(bad)


class SwissPairingTests(SimpleTestCase):
    def test_whole_round_avoids_greedy_dead_end(self):
        seeds = {i: i for i in range(1, 5)}
        allowed = {(1, 2), (1, 3), (2, 4)}
        results = history(
            [p for p in itertools.combinations(seeds, 2) if p not in allowed]
        )
        pairing = pair_swiss_round(
            seeds, standings(seeds, results), results, format=FIXED
        )
        self.assertEqual(set(pairing.pairs), {(1, 3), (2, 4)})
        self.assertEqual(pairing.repeat_pairs, ())

    def test_no_repeat_failure_and_minimum_override(self):
        seeds = {i: i for i in range(1, 5)}
        results = history([(1, 3), (1, 4), (2, 3), (2, 4), (3, 4)])
        rows = standings(seeds, results)
        with self.assertRaises(SwissPairingError):
            pair_swiss_round(seeds, rows, results, format=FIXED)
        pairing = pair_swiss_round(
            seeds, rows, results, format=FIXED, allow_rematches=True
        )
        self.assertEqual(pairing.pairs, ((1, 2), (3, 4)))
        self.assertEqual(pairing.repeat_pairs, ((3, 4),))

    def test_normal_solution_runs_first_even_when_override_requested(self):
        seeds = {i: i for i in range(1, 5)}
        results = history([(1, 4), (2, 3)])
        rows = standings(seeds, results)
        self.assertEqual(
            pair_swiss_round(seeds, rows, results, format=FIXED),
            pair_swiss_round(seeds, rows, results, format=FIXED, allow_rematches=True),
        )
        self.assertEqual(
            pair_swiss_round(
                seeds, rows, results, format=FIXED, allow_rematches=True
            ).repeat_pairs,
            (),
        )

    def test_first_round_last_seed_bye_and_folding(self):
        seeds = {i: i for i in range(1, 6)}
        pairing = pair_swiss_round(seeds, standings(seeds), (), format=FIXED)
        self.assertEqual(pairing.bye_entry_id, 5)
        self.assertEqual(pairing.pairs, ((1, 4), (2, 3)))

    def test_low_bye_candidate_strands_others(self):
        seeds = {i: i for i in range(1, 4)}
        results = history([(1, 2), (1, 3)])
        rows = standings(seeds, results)
        pairing = pair_swiss_round(
            seeds, rows, results, format=FIXED, allow_rematches=True
        )
        self.assertEqual(pairing.bye_entry_id, 1)
        self.assertEqual(pairing.pairs, ((2, 3),))
        self.assertEqual(pairing.repeat_pairs, ())

    def test_bye_count_precedes_low_score_then_worst_seed(self):
        seeds = {1: 1, 2: 2, 3: 3}
        results = [
            SwissResult(1, 1, 3, None, "BYE", winner_id=3),
            SwissResult(2, 1, 1, 2, "FORFEIT", winner_id=1),
        ]
        rows = standings(seeds, results)
        pairing = pair_swiss_round(seeds, rows, results, format=FIXED)
        self.assertEqual(pairing.bye_entry_id, 2)
        self.assertEqual(pairing.pairs, ((1, 3),))

    def test_bye_fairness_count_beats_points_and_threshold_record_beats_points(self):
        seeds = {1: 1, 2: 2, 3: 3}
        rows = [
            replace(r, points=Decimal(p), bye_count=int(r.entry_id == 3))
            for r, p in zip(standings(seeds), (6, 3, 0))
        ]
        self.assertEqual(
            pair_swiss_round(seeds, rows, (), format=FIXED).bye_entry_id, 2
        )
        rows = [
            replace(r, points=Decimal(p), wins=w, losses=loss)
            for r, p, w, loss in zip(
                standings(seeds), (0, 100, 50), (1, 0, 0), (0, 0, 1)
            )
        ]
        self.assertEqual(
            pair_swiss_round(seeds, rows, (), format=THRESHOLD).bye_entry_id, 3
        )

    def test_one_active_threshold_entry_receives_bye(self):
        seeds = {1: 1, 2: 2, 3: 3}
        results = history([(1, 2)])
        rows = standings(seeds, results, format=THRESHOLD, win_target=1, loss_limit=1)
        self.assertEqual(
            pair_swiss_round(seeds, rows, results, format=THRESHOLD).bye_entry_id, 3
        )
        with self.assertRaises(SwissPairingError):
            pair_swiss_round(
                seeds,
                [replace(r, status="ELIMINATED") for r in rows],
                results,
                format=THRESHOLD,
            )

    def test_adjacent_and_distant_score_group_moves(self):
        seeds = {i: i for i in range(1, 5)}
        rows = [
            replace(r, points=Decimal(p))
            for r, p in zip(standings(seeds), (9, 6, 3, 0))
        ]
        pairing = pair_swiss_round(seeds, rows, (), format=FIXED)
        self.assertEqual(pairing.pairs, ((1, 2), (3, 4)))
        self.assertEqual(pairing.cross_group_pairs, pairing.pairs)
        results = history([(1, 2)])
        pairing = pair_swiss_round(seeds, rows, results, format=FIXED)
        self.assertEqual(set(pairing.pairs), {(1, 3), (2, 4)})

    def test_tiny_exhaustive_reference_entire_preference_order(self):
        rng = random.Random(17)
        for format in (FIXED, THRESHOLD):
            for n in (4, 5, 6):
                seeds = dict(zip(range(1, n + 1), rng.sample(range(1, n + 1), n)))
                for _ in range(12):
                    edges = list(itertools.combinations(seeds, 2))
                    forbidden = [p for p in edges if rng.random() < 0.45]
                    results = history(forbidden)
                    rows = standings(seeds, results)
                    rows = [
                        replace(
                            r,
                            points=Decimal(rng.randrange(4)) / 4,
                            wins=rng.randrange(3),
                            losses=rng.randrange(3),
                            bye_count=rng.randrange(2),
                        )
                        for r in rows
                    ]
                    previous = {frozenset(p) for p in forbidden}
                    references = [
                        (pairs, bye)
                        for bye in (list(seeds) if n % 2 else [None])
                        for pairs in matchings([i for i in seeds if i != bye])
                    ]
                    normal = [
                        (pairs, bye)
                        for pairs, bye in references
                        if all(frozenset(p) not in previous for p in pairs)
                    ]
                    candidates = normal or references
                    best = min(
                        objective(pairs, bye, seeds, rows, previous, format)
                        for pairs, bye in candidates
                    )
                    actual = pair_swiss_round(
                        seeds, rows, results, format=format, allow_rematches=True
                    )
                    self.assertEqual(
                        objective(
                            actual.pairs,
                            actual.bye_entry_id,
                            seeds,
                            rows,
                            previous,
                            format,
                        ),
                        best,
                    )
                    self.assertEqual(
                        len(actual.pairs) * 2 + (actual.bye_entry_id is not None), n
                    )

    def test_incomplete_or_ineligible_input_is_rejected(self):
        seeds = {i: i for i in range(1, 5)}
        rows = standings(seeds)
        for invalid in (
            rows[:-1],
            rows + rows[:1],
            [replace(rows[0], entry_id=99), *rows[1:]],
            [replace(rows[0], status="WITHDRAWN"), *rows[1:]],
            [replace(rows[0], status="QUALIFIED"), *rows[1:]],
        ):
            with self.assertRaises(SwissPairingError):
                pair_swiss_round(seeds, invalid, (), format=FIXED)
        with self.assertRaises(SwissPairingError):
            pair_swiss_round(seeds, rows, [SwissResult(1, 1, 1, 2, "")], format=FIXED)

    def test_input_permutations_hash_seeds_and_canonical_output(self):
        script = """
import json, random
from dataclasses import replace
from decimal import Decimal
from competitions.swiss import rank_swiss, pair_swiss_round, SwissResult
seeds = {80: 1, 30: 2, 90: 3, 20: 4, 60: 5, 10: 6, 70: 7}
rng = random.Random(PERMUTATION)
items = list(seeds.items()); rng.shuffle(items); seeds = dict(items)
results = [SwissResult(1, 1, 80, 30, "FORFEIT", winner_id=80), SwissResult(2, 1, 90, 20, "FORFEIT", winner_id=90)]
rng.shuffle(results)
payload = []
for format in ("SWISS_FIXED", "SWISS_THRESHOLD"):
    kwargs = {"win_target": 4, "loss_limit": 4} if format == "SWISS_THRESHOLD" else {}
    rows = rank_swiss(seeds, results, format=format, points=(Decimal(3), Decimal(1), Decimal(0)), tiebreaks=(), **kwargs)
    rng.shuffle(rows)
    pairing = pair_swiss_round(seeds, rows, results, format=format, allow_rematches=True)
    payload.append([pairing.pairs, pairing.bye_entry_id, pairing.repeat_pairs, pairing.cross_group_pairs])
print(json.dumps(payload))
"""
        outputs = []
        for hash_seed in (1, 7, 73):
            for permutation in (0, 1, 2):
                outputs.append(
                    subprocess.check_output(
                        [
                            sys.executable,
                            "-c",
                            script.replace("PERMUTATION", str(permutation)),
                        ],
                        env={**os.environ, "PYTHONHASHSEED": str(hash_seed)},
                        text=True,
                    ).strip()
                )
        self.assertEqual(len(set(outputs)), 1)
        seeds = {80: 1, 30: 2, 90: 3, 20: 4, 60: 5, 10: 6, 70: 7}
        for pairs, bye, _, _ in json.loads(outputs[0]):
            self.assertTrue(all(seeds[a] < seeds[b] for a, b in pairs))
            self.assertEqual(
                pairs, sorted(pairs, key=lambda p: (seeds[p[0]], seeds[p[1]]))
            )
            self.assertNotIn(bye, [i for p in pairs for i in p])


class SwissValidationTests(SimpleTestCase):
    def test_invalid_point_values(self):
        for points in (
            (Decimal("NaN"), Decimal(1), Decimal(0)),
            (Decimal("Infinity"), Decimal(1), Decimal(0)),
            (Decimal(-1), Decimal(1), Decimal(0)),
            (3, 1, 0),
            (Decimal(3),),
        ):
            with self.assertRaises(ValueError):
                standings({1: 1, 2: 2}, points=points)

    def test_result_round_ids_and_immutability(self):
        from dataclasses import FrozenInstanceError

        result = SwissResult(1, 1, 1, 2, "FORFEIT", winner_id=1)
        with self.assertRaises(FrozenInstanceError):
            result.round_number = 2
        for invalid in (
            replace(result, round_number=True),
            replace(result, round_number=0),
            replace(result, round_number=65),
            replace(result, match_id=True),
            replace(result, winner_id=True),
            replace(result, side_one_score=1),
        ):
            with self.assertRaises(ValueError):
                standings({1: 1, 2: 2}, [invalid])
        with self.assertRaises(ValueError):
            standings({1: 1, 2: 2}, [result, replace(result, round_number=2)])

    def test_pairing_rejects_invalid_records_boolean_ids_and_flags(self):
        seeds = {1: 1, 2: 2}
        rows = standings(seeds)
        for invalid in (
            replace(rows[0], entry_id=True),
            replace(rows[0], wins=True),
            replace(rows[0], bye_count=-1),
            replace(rows[0], points=Decimal("NaN")),
        ):
            with self.assertRaises(SwissPairingError):
                pair_swiss_round(seeds, [invalid, rows[1]], (), format=FIXED)
        with self.assertRaises(SwissPairingError):
            pair_swiss_round(seeds, rows, (), format=FIXED, allow_rematches="yes")
