from dataclasses import dataclass


@dataclass(frozen=True)
class SeedSlot:
    seed: int


@dataclass(frozen=True)
class WinnerSlot:
    round_number: int
    match_number: int


@dataclass(frozen=True)
class GeneratedMatch:
    number: int
    slots: tuple[SeedSlot | WinnerSlot, SeedSlot | WinnerSlot]


@dataclass(frozen=True)
class GeneratedRound:
    number: int
    matches: tuple[GeneratedMatch, ...]


def seed_order(field_size: int) -> tuple[int, ...]:
    if field_size < 2 or field_size & (field_size - 1):
        raise ValueError("Field size must be a power of two of at least two.")
    order = [1, 2]
    while len(order) < field_size:
        next_size = len(order) * 2
        order = [seed for value in order for seed in (value, next_size + 1 - value)]
    return tuple(order)


def generate_single_elimination(entrant_count: int) -> tuple[GeneratedRound, ...]:
    if entrant_count < 2:
        raise ValueError("At least two entrants are required.")
    field_size = 1 << (entrant_count - 1).bit_length()
    ordered_seeds = seed_order(field_size)
    rounds: list[GeneratedRound] = []
    first_matches = tuple(
        GeneratedMatch(
            number=index // 2 + 1,
            slots=(SeedSlot(ordered_seeds[index]), SeedSlot(ordered_seeds[index + 1])),
        )
        for index in range(0, field_size, 2)
    )
    rounds.append(GeneratedRound(number=1, matches=first_matches))
    previous_count = len(first_matches)
    round_number = 2
    while previous_count > 1:
        matches = tuple(
            GeneratedMatch(
                number=index // 2 + 1,
                slots=(
                    WinnerSlot(round_number - 1, index + 1),
                    WinnerSlot(round_number - 1, index + 2),
                ),
            )
            for index in range(0, previous_count, 2)
        )
        rounds.append(GeneratedRound(number=round_number, matches=matches))
        previous_count = len(matches)
        round_number += 1
    return tuple(rounds)
