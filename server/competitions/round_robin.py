from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby


TIEBREAKS = ("HEAD_TO_HEAD", "MATCH_WINS", "GAME_DIFFERENCE", "GAMES_WON")
DEFAULT_TIEBREAKS = ("HEAD_TO_HEAD", "GAME_DIFFERENCE", "GAMES_WON")


@dataclass(frozen=True)
class RoundRobinRound:
    number: int
    pairings: tuple[tuple[int, int], ...]
    resting_entry_id: int | None = None


@dataclass(frozen=True)
class RoundRobinResult:
    match_id: int
    side_one_id: int
    side_two_id: int
    outcome: str
    side_one_score: int | None
    side_two_score: int | None
    winner_id: int | None


@dataclass
class Standing:
    entry_id: int
    rank: int = 1
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: Decimal = Decimal("0")
    games_won: int = 0
    game_difference: int = 0


def _validate_field(ids: Sequence[int]) -> None:
    if not 2 <= len(ids) <= 256 or len(set(ids)) != len(ids):
        raise ValueError("A field requires 2–256 unique entrants.")


def allocate_snake_groups(
    ordered_ids: Sequence[int], group_count: int
) -> tuple[tuple[int, ...], ...]:
    _validate_field(ordered_ids)
    if type(group_count) is not int or not 1 <= group_count <= len(ordered_ids) // 2:
        raise ValueError("Each group needs at least two entrants.")
    groups = [[] for _ in range(group_count)]
    for index, entry_id in enumerate(ordered_ids):
        cycle, position = divmod(index, group_count)
        groups[group_count - position - 1 if cycle % 2 else position].append(entry_id)
    return tuple(tuple(group) for group in groups)


def generate_round_robin(
    entry_ids: Sequence[int], *, meetings: int
) -> tuple[RoundRobinRound, ...]:
    _validate_field(entry_ids)
    if type(meetings) is not int or meetings not in (1, 2):
        raise ValueError("Choose one or two meetings per pair.")
    ring = list(entry_ids)
    if len(ring) % 2:
        ring.append(None)
    rounds = []
    for number in range(1, len(ring)):
        pairs = []
        rest = None
        for position in range(len(ring) // 2):
            first, second = ring[position], ring[-position - 1]
            if first is None or second is None:
                rest = second if first is None else first
            else:
                pairs.append((first, second))
        rounds.append(RoundRobinRound(number, tuple(pairs), rest))
        ring = [ring[0], ring[-1], *ring[1:-1]]
    if meetings == 2:
        offset = len(rounds)
        rounds.extend(
            RoundRobinRound(
                round_.number + offset,
                tuple((b, a) for a, b in round_.pairings),
                round_.resting_entry_id,
            )
            for round_ in tuple(rounds)
        )
    return tuple(rounds)


def _match_points(
    result: RoundRobinResult, points: tuple[Decimal, Decimal, Decimal]
) -> tuple[Decimal, Decimal]:
    win, draw, loss = points
    if result.outcome == "DOUBLE_FORFEIT":
        return Decimal("0"), Decimal("0")
    if result.winner_id == result.side_one_id:
        return win, loss
    if result.winner_id == result.side_two_id:
        return loss, win
    return draw, draw


def rank_group(
    entry_ids: Sequence[int],
    results: Sequence[RoundRobinResult],
    *,
    points: tuple[Decimal, Decimal, Decimal],
    tiebreaks: Sequence[str],
) -> tuple[Standing, ...]:
    _validate_field(entry_ids)
    if len(set(tiebreaks)) != len(tiebreaks) or any(
        rule not in TIEBREAKS for rule in tiebreaks
    ):
        raise ValueError("Choose each supported tiebreaker at most once.")
    rows = {entry_id: Standing(entry_id) for entry_id in entry_ids}
    for result in results:
        first, second = rows[result.side_one_id], rows[result.side_two_id]
        first.played += 1
        second.played += 1
        one_points, two_points = _match_points(result, points)
        first.points += one_points
        second.points += two_points
        if result.outcome == "DOUBLE_FORFEIT":
            first.losses += 1
            second.losses += 1
        elif result.winner_id:
            winner, loser = (
                (first, second)
                if result.winner_id == first.entry_id
                else (second, first)
            )
            winner.wins += 1
            loser.losses += 1
        else:
            first.draws += 1
            second.draws += 1
        if result.outcome == "PLAYED":
            first.games_won += result.side_one_score
            second.games_won += result.side_two_score
            difference = result.side_one_score - result.side_two_score
            first.game_difference += difference
            second.game_difference -= difference

    def split(block, values):
        ordered = sorted(block, key=lambda row: values[row.entry_id], reverse=True)
        return [
            list(group)
            for _, group in groupby(ordered, key=lambda row: values[row.entry_id])
        ]

    blocks = split(
        list(rows.values()), {entry: row.points for entry, row in rows.items()}
    )
    for rule in tiebreaks:
        refined = []
        for block in blocks:
            if rule == "HEAD_TO_HEAD":
                ids = {row.entry_id for row in block}
                values = dict.fromkeys(ids, Decimal("0"))
                for result in results:
                    if result.side_one_id in ids and result.side_two_id in ids:
                        first, second = _match_points(result, points)
                        values[result.side_one_id] += first
                        values[result.side_two_id] += second
            else:
                field = {
                    "MATCH_WINS": "wins",
                    "GAME_DIFFERENCE": "game_difference",
                    "GAMES_WON": "games_won",
                }[rule]
                values = {row.entry_id: getattr(row, field) for row in block}
            refined.extend(split(block, values))
        blocks = refined
    ranked = []
    for block in blocks:
        rank = len(ranked) + 1
        for row in block:
            row.rank = rank
        ranked.extend(block)
    return tuple(ranked)
