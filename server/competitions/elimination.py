from dataclasses import dataclass


@dataclass(frozen=True)
class SeedSlot:
    seed: int


@dataclass(frozen=True)
class WinnerSlot:
    round_number: int
    match_number: int
    section: str = "NORMAL"


@dataclass(frozen=True)
class LoserSlot:
    round_number: int
    match_number: int
    section: str


@dataclass(frozen=True)
class GeneratedMatch:
    number: int
    slots: tuple[SeedSlot | WinnerSlot | LoserSlot, SeedSlot | WinnerSlot | LoserSlot]


@dataclass(frozen=True)
class GeneratedRound:
    number: int
    matches: tuple[GeneratedMatch, ...]
    section: str = "NORMAL"


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


def generate_double_elimination(
    entrant_count: int, *, grand_final_policy: str
) -> tuple[GeneratedRound, ...]:
    if not 2 <= entrant_count <= 256:
        raise ValueError("Entrant count must be between two and 256.")
    if grand_final_policy not in {"RESET", "NO_RESET"}:
        raise ValueError("Grand final policy must be RESET or NO_RESET.")

    upper = tuple(
        GeneratedRound(
            number=round_.number,
            matches=tuple(
                GeneratedMatch(
                    number=match.number,
                    slots=tuple(
                        WinnerSlot(slot.round_number, slot.match_number, "UPPER")
                        if isinstance(slot, WinnerSlot)
                        else slot
                        for slot in match.slots
                    ),
                )
                for match in round_.matches
            ),
            section="UPPER",
        )
        for round_ in generate_single_elimination(entrant_count)
    )
    field_size = 1 << (entrant_count - 1).bit_length()
    lower: list[GeneratedRound] = []

    if field_size >= 4:
        previous_count = field_size // 4
        lower.append(
            GeneratedRound(
                number=1,
                matches=tuple(
                    GeneratedMatch(
                        number=index + 1,
                        slots=(
                            LoserSlot(1, index * 2 + 1, "UPPER"),
                            LoserSlot(1, index * 2 + 2, "UPPER"),
                        ),
                    )
                    for index in range(previous_count)
                ),
                section="LOWER",
            )
        )
        lower_number = 1
        for upper_number in range(2, len(upper) + 1):
            if upper_number > 2:
                lower_number += 1
                lower.append(
                    GeneratedRound(
                        number=lower_number,
                        matches=tuple(
                            GeneratedMatch(
                                number=index // 2 + 1,
                                slots=(
                                    WinnerSlot(lower_number - 1, index + 1, "LOWER"),
                                    WinnerSlot(lower_number - 1, index + 2, "LOWER"),
                                ),
                            )
                            for index in range(0, previous_count, 2)
                        ),
                        section="LOWER",
                    )
                )
                previous_count //= 2

            lower_number += 1
            lower.append(
                GeneratedRound(
                    number=lower_number,
                    matches=tuple(
                        GeneratedMatch(
                            number=index + 1,
                            slots=(
                                WinnerSlot(lower_number - 1, index + 1, "LOWER"),
                                LoserSlot(
                                    upper_number,
                                    previous_count - index,
                                    "UPPER",
                                ),
                            ),
                        )
                        for index in range(previous_count)
                    ),
                    section="LOWER",
                )
            )

    final_lower_slot = (
        WinnerSlot(lower[-1].number, 1, "LOWER") if lower else LoserSlot(1, 1, "UPPER")
    )
    finals = [
        GeneratedRound(
            number=1,
            matches=(
                GeneratedMatch(
                    number=1,
                    slots=(
                        WinnerSlot(upper[-1].number, 1, "UPPER"),
                        final_lower_slot,
                    ),
                ),
            ),
            section="FINALS",
        )
    ]
    if grand_final_policy == "RESET":
        finals.append(
            GeneratedRound(
                number=2,
                matches=(
                    GeneratedMatch(
                        number=1,
                        slots=(
                            LoserSlot(1, 1, "FINALS"),
                            WinnerSlot(1, 1, "FINALS"),
                        ),
                    ),
                ),
                section="FINALS",
            )
        )
    return upper + tuple(lower) + tuple(finals)


@dataclass(frozen=True)
class EliminationResult:
    round_number: int
    section: str
    status: str
    outcome: str
    side_one_id: int | None
    side_two_id: int | None
    winner_id: int | None


@dataclass(frozen=True)
class PlacementBands:
    bands: tuple[tuple[int, ...], ...]
    unranked_entry_ids: tuple[int, ...]


def finishing_bands(entry_ids, results, *, format: str) -> PlacementBands:
    """Rank terminal losses; structural matches never invent finishers."""
    if format not in ("SINGLE_ELIMINATION", "DOUBLE_ELIMINATION"):
        raise ValueError("Unsupported elimination format.")
    entries = set(entry_ids)
    ordinary = [r for r in results if r.section != "TIEBREAK" and r.status == "FINAL"]
    final_section = "FINALS" if format == "DOUBLE_ELIMINATION" else "NORMAL"
    finals = [r for r in ordinary if r.section == final_section]
    final = max(finals, key=lambda r: r.round_number, default=None)
    bands = []
    ranked = set()
    if final:
        finalists = {i for i in (final.side_one_id, final.side_two_id) if i in entries}
        if final.winner_id in finalists:
            bands.append((final.winner_id,))
            remainder = finalists - {final.winner_id}
            if remainder:
                bands.append(tuple(sorted(remainder)))
        elif final.outcome == "DOUBLE_FORFEIT" and finalists:
            bands.append(tuple(sorted(finalists)))
        ranked.update(i for band in bands for i in band)
    section = "LOWER" if format == "DOUBLE_ELIMINATION" else "NORMAL"
    exits = {}
    for result in ordinary:
        if result.section != section or result.outcome in ("BYE", "EMPTY"):
            continue
        for entrant in (result.side_one_id, result.side_two_id):
            if (
                entrant in entries
                and entrant != result.winner_id
                and entrant not in ranked
            ):
                if entrant in exits:
                    raise ValueError("An entrant has multiple terminal exits.")
                exits[entrant] = result.round_number
    # An undefined upper exit cannot be ordered against terminal lower losses.
    uncertain = entries - ranked - set(exits)
    if format != "DOUBLE_ELIMINATION" or not uncertain:
        for depth in sorted(set(exits.values()), reverse=True):
            band = tuple(sorted(i for i, round_ in exits.items() if round_ == depth))
            bands.append(band)
            ranked.update(band)
    return PlacementBands(tuple(bands), tuple(sorted(entries - ranked)))
