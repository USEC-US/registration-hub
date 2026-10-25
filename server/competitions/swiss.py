"""Pure Swiss setup, standings and whole-round matching calculations."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

import networkx as nx


FIXED = "SWISS_FIXED"
THRESHOLD = "SWISS_THRESHOLD"
TIEBREAKS = ("OPPONENT_POINTS", "GAME_DIFFERENCE", "GAMES_WON", "MATCH_WINS")
DEFAULT_TIEBREAKS = TIEBREAKS[:3]


class SwissPairingError(ValueError):
    pass


@dataclass(frozen=True)
class SwissResult:
    match_id: int
    round_number: int
    side_one_id: int
    side_two_id: int | None
    outcome: str
    side_one_score: int | None = None
    side_two_score: int | None = None
    winner_id: int | None = None


@dataclass
class SwissStanding:
    entry_id: int
    rank: int = 1
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: Decimal = Decimal("0")
    games_won: int = 0
    game_difference: int = 0
    opponent_points: Decimal = Decimal("0")
    bye_count: int = 0
    status: str = "ACTIVE"


@dataclass(frozen=True)
class SwissPairing:
    pairs: tuple[tuple[int, int], ...]
    bye_entry_id: int | None = None
    repeat_pairs: tuple[tuple[int, int], ...] = ()
    cross_group_pairs: tuple[tuple[int, int], ...] = ()


def resolve_round_limit(
    entrant_count: int,
    *,
    format: str,
    round_count: int | None,
    win_target: int | None,
    loss_limit: int | None,
) -> int:
    if type(entrant_count) is not int or not 2 <= entrant_count <= 256:
        raise ValueError("A Swiss field requires 2–256 entrants.")
    cap = min(64, entrant_count - 1 if entrant_count % 2 == 0 else entrant_count)
    if format == FIXED:
        if win_target is not None or loss_limit is not None:
            raise ValueError("Fixed Swiss uses a round count, not win/loss targets.")
        resolved = (
            (entrant_count - 1).bit_length() if round_count is None else round_count
        )
        if type(resolved) is not int or not 1 <= resolved <= cap:
            raise ValueError(f"Choose 1–{cap} Swiss rounds for this field.")
        return resolved
    if format == THRESHOLD:
        if round_count is not None or any(
            type(v) is not int or v < 1 for v in (win_target, loss_limit)
        ):
            raise ValueError("Threshold Swiss needs positive integer win/loss targets.")
        resolved = win_target + loss_limit - 1
        if resolved > cap:
            raise ValueError(
                f"Win target plus loss limit minus one cannot exceed {cap}."
            )
        return resolved
    raise ValueError("Choose a Swiss format.")


def _validate_seeds(entry_seeds: Mapping[int, int], format: str) -> None:
    if format not in (FIXED, THRESHOLD):
        raise ValueError("Choose a Swiss format.")
    if (
        not 2 <= len(entry_seeds) <= 256
        or any(
            type(entry) is not int or entry < 1 or type(seed) is not int or seed < 1
            for entry, seed in entry_seeds.items()
        )
        or len(set(entry_seeds.values())) != len(entry_seeds)
    ):
        raise ValueError(
            "A Swiss field requires 2–256 entrants with unique positive saved seeds."
        )


def _validate_results(entry_seeds, results, format):
    appearances, match_ids = set(), set()
    for result in results:
        if (
            type(result.match_id) is not int
            or result.match_id < 1
            or result.match_id in match_ids
        ):
            raise ValueError("Result match IDs must be unique positive integers.")
        match_ids.add(result.match_id)
        if type(result.round_number) is not int or not 1 <= result.round_number <= 64:
            raise ValueError("Swiss result rounds must be between 1 and 64.")
        ids = (
            (result.side_one_id,)
            if result.side_two_id is None
            else (result.side_one_id, result.side_two_id)
        )
        if len(set(ids)) != len(ids) or any(
            type(i) is not int or i not in entry_seeds for i in ids
        ):
            raise ValueError("Each result needs distinct entrants from this stage.")
        for entry in ids:
            appearance = (result.round_number, entry)
            if appearance in appearances:
                raise ValueError("An entrant can appear only once per Swiss round.")
            appearances.add(appearance)
        if result.outcome == "BYE":
            valid = (
                result.side_two_id is None and result.winner_id == result.side_one_id
            )
        elif result.side_two_id is None:
            valid = False
        elif result.outcome == "DOUBLE_FORFEIT":
            valid = result.winner_id is None
        elif result.outcome == "FORFEIT":
            valid = type(result.winner_id) is int and result.winner_id in ids
        elif result.outcome == "PLAYED":
            one, two = result.side_one_score, result.side_two_score
            valid = all(type(s) is int and s >= 0 for s in (one, two))
            if valid:
                winner = (
                    result.side_one_id
                    if one > two
                    else result.side_two_id
                    if two > one
                    else None
                )
                valid = result.winner_id == winner and (
                    winner is not None or format == FIXED
                )
        else:
            valid = False
        if result.outcome != "PLAYED" and (
            result.side_one_score is not None or result.side_two_score is not None
        ):
            valid = False
        if result.winner_id is not None and type(result.winner_id) is not int:
            valid = False
        if not valid:
            raise ValueError(
                "Swiss standings require complete, consistent final results."
            )


def rank_swiss(
    entry_seeds: Mapping[int, int],
    results: Sequence[SwissResult],
    *,
    format: str,
    points: tuple[Decimal, Decimal, Decimal],
    tiebreaks: Sequence[str],
    win_target: int | None = None,
    loss_limit: int | None = None,
) -> list[SwissStanding]:
    _validate_seeds(entry_seeds, format)
    resolve_round_limit(
        len(entry_seeds),
        format=format,
        round_count=None,
        win_target=win_target,
        loss_limit=loss_limit,
    )
    if len(points) != 3 or any(
        not isinstance(p, Decimal) or not p.is_finite() or p < 0 for p in points
    ):
        raise ValueError("Use three finite nonnegative Decimal point values.")
    if len(set(tiebreaks)) != len(tiebreaks) or any(
        rule not in TIEBREAKS for rule in tiebreaks
    ):
        raise ValueError("Choose each supported Swiss tiebreaker at most once.")
    _validate_results(entry_seeds, results, format)
    rows = {
        entry: SwissStanding(entry)
        for entry in sorted(entry_seeds, key=entry_seeds.get)
    }
    opponents = {entry: [] for entry in rows}
    for result in sorted(results, key=lambda r: r.round_number):
        ids = (
            (result.side_one_id,)
            if result.side_two_id is None
            else (result.side_one_id, result.side_two_id)
        )
        if any(rows[i].status != "ACTIVE" for i in ids):
            raise ValueError(
                "An entrant cannot play after qualifying or being eliminated."
            )
        for entry in ids:
            row = rows[entry]
            row.played += 1
            if result.outcome == "DOUBLE_FORFEIT":
                row.losses += 1
            elif result.winner_id == entry:
                row.wins += 1
                row.points += points[0]
            elif result.winner_id is None:
                row.draws += 1
                row.points += points[1]
            else:
                row.losses += 1
                row.points += points[2]
            if result.outcome == "BYE":
                row.bye_count += 1
            if result.outcome == "PLAYED":
                own, other = (
                    (result.side_one_score, result.side_two_score)
                    if entry == result.side_one_id
                    else (result.side_two_score, result.side_one_score)
                )
                row.games_won += own
                row.game_difference += own - other
            if format == THRESHOLD:
                if row.wins >= win_target:
                    row.status = "QUALIFIED"
                elif row.losses >= loss_limit:
                    row.status = "ELIMINATED"
        if len(ids) == 2:
            opponents[ids[0]].append(ids[1])
            opponents[ids[1]].append(ids[0])
    for entry, row in rows.items():
        row.opponent_points = sum(
            (rows[other].points for other in opponents[entry]), Decimal("0")
        )
    fields = {
        "OPPONENT_POINTS": "opponent_points",
        "GAME_DIFFERENCE": "game_difference",
        "GAMES_WON": "games_won",
        "MATCH_WINS": "wins",
    }

    def competitive_key(row):
        base = (row.points,) if format == FIXED else (row.wins, -row.losses)
        return (*base, *(getattr(row, fields[rule]) for rule in tiebreaks))

    ordered = sorted(rows.values(), key=competitive_key, reverse=True)
    previous = None
    for position, row in enumerate(ordered, 1):
        key = competitive_key(row)
        if key != previous:
            rank = position
        row.rank = rank
        previous = key
    return ordered


def pair_swiss_round(
    entry_seeds: Mapping[int, int],
    standings: Sequence[SwissStanding],
    results: Sequence[SwissResult],
    *,
    format: str,
    allow_rematches: bool = False,
) -> SwissPairing:
    try:
        _validate_seeds(entry_seeds, format)
        _validate_results(entry_seeds, results, format)
        if type(allow_rematches) is not bool:
            raise ValueError("The rematch exception must be an explicit boolean.")
        if (
            len(standings) != len(entry_seeds)
            or any(type(r.entry_id) is not int for r in standings)
            or {r.entry_id for r in standings} != set(entry_seeds)
        ):
            raise ValueError("Supply exactly one standing for every stage entrant.")
        if any(
            r.status not in ("ACTIVE", "QUALIFIED", "ELIMINATED")
            or (format == FIXED and r.status != "ACTIVE")
            for r in standings
        ):
            raise ValueError("Standings contain an ineligible entrant status.")
        if any(
            any(
                type(v) is not int or v < 0
                for v in (r.played, r.wins, r.draws, r.losses, r.bye_count)
            )
            or not isinstance(r.points, Decimal)
            or not r.points.is_finite()
            or r.points < 0
            for r in standings
        ):
            raise ValueError("Standings contain invalid points or records.")
    except ValueError as exc:
        raise SwissPairingError(str(exc)) from exc
    rows = {r.entry_id: r for r in standings}

    def group(entry):
        row = rows[entry]
        return (row.points,) if format == FIXED else (row.wins, -row.losses)

    active = sorted(
        (r.entry_id for r in standings if r.status == "ACTIVE"),
        key=lambda entry: (*(-value for value in group(entry)), entry_seeds[entry]),
    )
    if not active:
        raise SwissPairingError("There are no active entrants for another Swiss round.")
    previous = {
        frozenset((r.side_one_id, r.side_two_id))
        for r in results
        if r.side_two_id is not None
    }

    for permit_repeats in (False, True) if allow_rematches else (False,):
        graph = nx.Graph()
        graph.add_nodes_from(active)
        graph.add_edges_from(
            (a, b, {"weight": 0})
            for a, b in combinations(active, 2)
            if permit_repeats or frozenset((a, b)) not in previous
        )
        bye = None
        if len(active) % 2:
            # A dummy selects the fairest feasible bye before folding the remaining seeds.
            graph.add_node(0)
            candidates = sorted(
                active, key=lambda i: (rows[i].bye_count, *group(i), -entry_seeds[i])
            )
            graph.add_edges_from(
                (0, entry, {"weight": position})
                for position, entry in enumerate(candidates)
            )
            feasible = nx.min_weight_matching(graph)
            if len(feasible) * 2 != len(graph):
                continue
            bye = next(a if b == 0 else b for a, b in feasible if a == 0 or b == 0)
            graph.remove_nodes_from((0, bye))
        members = [i for i in active if i != bye]
        groups = {}
        for entry in members:
            groups.setdefault(group(entry), []).append(entry)
        positions = {}
        for first, second in combinations(groups, 2):
            merged = sorted(groups[first] + groups[second], key=entry_seeds.get)
            positions[frozenset((first, second))] = (
                {entry: i for i, entry in enumerate(merged)},
                len(merged),
            )
        for key, ids in groups.items():
            positions[frozenset((key,))] = (
                {entry: i for i, entry in enumerate(ids)},
                len(ids),
            )
        scale = (
            10
            ** max(
                (max(0, -rows[i].points.as_tuple().exponent) for i in members),
                default=0,
            )
            if format == FIXED
            else 1
        )
        metrics = {}
        for a, b in graph.edges:
            order, size = positions[frozenset((group(a), group(b)))]
            distance = (
                int(abs(rows[a].points - rows[b].points) * scale)
                if format == FIXED
                else abs(rows[a].wins - rows[b].wins)
                + abs(rows[a].losses - rows[b].losses)
            )
            metrics[a, b] = (
                int(frozenset((a, b)) in previous),
                int(group(a) != group(b)),
                distance,
                abs(order[a] + order[b] - (size - 1)),
            )
        # Each multiplier exceeds the maximum possible sum of all lower priorities.
        pair_count = len(members) // 2
        lower_bound, multipliers = 0, []
        for priority in reversed(range(4)):
            multiplier = lower_bound + 1
            multipliers.insert(0, multiplier)
            lower_bound += (
                pair_count
                * max((m[priority] for m in metrics.values()), default=0)
                * multiplier
            )
        for edge, values in metrics.items():
            graph.edges[edge]["weight"] = sum(
                v * m for v, m in zip(values, multipliers)
            )
        matching = nx.min_weight_matching(graph)
        if len(matching) * 2 != len(members):
            continue
        pairs = tuple(
            sorted(
                (tuple(sorted(pair, key=entry_seeds.get)) for pair in matching),
                key=lambda p: (entry_seeds[p[0]], entry_seeds[p[1]]),
            )
        )
        return SwissPairing(
            pairs,
            bye,
            tuple(p for p in pairs if frozenset(p) in previous),
            tuple(p for p in pairs if group(p[0]) != group(p[1])),
        )
    raise SwissPairingError(
        "No complete Swiss round is possible without a confirmed rematch exception."
    )
