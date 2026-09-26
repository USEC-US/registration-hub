from django.test import SimpleTestCase

from competitions.elimination import (
    GeneratedMatch,
    GeneratedRound,
    LoserSlot,
    SeedSlot,
    WinnerSlot,
    generate_double_elimination,
    generate_single_elimination,
    seed_order,
)


class SingleEliminationGeneratorTests(SimpleTestCase):
    def test_supported_small_fields_have_unique_seeds_and_acyclic_routes(self):
        for entrant_count in (2, 3, 4, 5, 8, 16):
            with self.subTest(entrant_count=entrant_count):
                rounds = generate_single_elimination(entrant_count)
                field_size = 1 << (entrant_count - 1).bit_length()
                self.assertEqual(
                    sum(len(round_.matches) for round_ in rounds), field_size - 1
                )
                self.assertEqual(
                    sorted(
                        slot.seed
                        for match in rounds[0].matches
                        for slot in match.slots
                        if isinstance(slot, SeedSlot)
                    ),
                    list(range(1, field_size + 1)),
                )
                for round_ in rounds[1:]:
                    self.assertTrue(
                        all(
                            isinstance(slot, WinnerSlot)
                            and slot.round_number == round_.number - 1
                            for match in round_.matches
                            for slot in match.slots
                        )
                    )

    def test_standard_seed_order(self):
        self.assertEqual(seed_order(8), (1, 8, 4, 5, 2, 7, 3, 6))

    def test_uneven_field_uses_next_power_of_two_and_fixed_winner_routes(self):
        rounds = generate_single_elimination(5)

        self.assertEqual([len(round_.matches) for round_ in rounds], [4, 2, 1])
        self.assertEqual(
            rounds[0].matches[0].slots,
            (SeedSlot(1), SeedSlot(8)),
        )
        self.assertEqual(
            rounds[1].matches[0].slots,
            (WinnerSlot(1, 1), WinnerSlot(1, 2)),
        )
        self.assertEqual(
            rounds[2].matches[0].slots,
            (WinnerSlot(2, 1), WinnerSlot(2, 2)),
        )

    def test_rejects_invalid_fields(self):
        with self.assertRaises(ValueError):
            seed_order(3)
        with self.assertRaises(ValueError):
            generate_single_elimination(1)


class DoubleEliminationGeneratorTests(SimpleTestCase):
    @staticmethod
    def round(section, number, *slots):
        return GeneratedRound(
            number=number,
            matches=tuple(
                GeneratedMatch(number=index, slots=match_slots)
                for index, match_slots in enumerate(slots, 1)
            ),
            section=section,
        )

    def test_exact_two_entrant_reset_routing(self):
        self.assertEqual(
            generate_double_elimination(2, grand_final_policy="RESET"),
            (
                self.round("UPPER", 1, (SeedSlot(1), SeedSlot(2))),
                self.round(
                    "FINALS",
                    1,
                    (WinnerSlot(1, 1, "UPPER"), LoserSlot(1, 1, "UPPER")),
                ),
                self.round(
                    "FINALS",
                    2,
                    (LoserSlot(1, 1, "FINALS"), WinnerSlot(1, 1, "FINALS")),
                ),
            ),
        )

    def test_exact_four_entrant_reset_routing(self):
        self.assertEqual(
            generate_double_elimination(4, grand_final_policy="RESET"),
            (
                self.round(
                    "UPPER",
                    1,
                    (SeedSlot(1), SeedSlot(4)),
                    (SeedSlot(2), SeedSlot(3)),
                ),
                self.round(
                    "UPPER",
                    2,
                    (WinnerSlot(1, 1, "UPPER"), WinnerSlot(1, 2, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    1,
                    (LoserSlot(1, 1, "UPPER"), LoserSlot(1, 2, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    2,
                    (WinnerSlot(1, 1, "LOWER"), LoserSlot(2, 1, "UPPER")),
                ),
                self.round(
                    "FINALS",
                    1,
                    (WinnerSlot(2, 1, "UPPER"), WinnerSlot(2, 1, "LOWER")),
                ),
                self.round(
                    "FINALS",
                    2,
                    (LoserSlot(1, 1, "FINALS"), WinnerSlot(1, 1, "FINALS")),
                ),
            ),
        )

    def test_exact_eight_entrant_reset_routing_reverses_upper_drop_order(self):
        self.assertEqual(
            generate_double_elimination(8, grand_final_policy="RESET"),
            (
                self.round(
                    "UPPER",
                    1,
                    (SeedSlot(1), SeedSlot(8)),
                    (SeedSlot(4), SeedSlot(5)),
                    (SeedSlot(2), SeedSlot(7)),
                    (SeedSlot(3), SeedSlot(6)),
                ),
                self.round(
                    "UPPER",
                    2,
                    (WinnerSlot(1, 1, "UPPER"), WinnerSlot(1, 2, "UPPER")),
                    (WinnerSlot(1, 3, "UPPER"), WinnerSlot(1, 4, "UPPER")),
                ),
                self.round(
                    "UPPER",
                    3,
                    (WinnerSlot(2, 1, "UPPER"), WinnerSlot(2, 2, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    1,
                    (LoserSlot(1, 1, "UPPER"), LoserSlot(1, 2, "UPPER")),
                    (LoserSlot(1, 3, "UPPER"), LoserSlot(1, 4, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    2,
                    (WinnerSlot(1, 1, "LOWER"), LoserSlot(2, 2, "UPPER")),
                    (WinnerSlot(1, 2, "LOWER"), LoserSlot(2, 1, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    3,
                    (WinnerSlot(2, 1, "LOWER"), WinnerSlot(2, 2, "LOWER")),
                ),
                self.round(
                    "LOWER",
                    4,
                    (WinnerSlot(3, 1, "LOWER"), LoserSlot(3, 1, "UPPER")),
                ),
                self.round(
                    "FINALS",
                    1,
                    (WinnerSlot(3, 1, "UPPER"), WinnerSlot(4, 1, "LOWER")),
                ),
                self.round(
                    "FINALS",
                    2,
                    (LoserSlot(1, 1, "FINALS"), WinnerSlot(1, 1, "FINALS")),
                ),
            ),
        )

    def test_exact_sixteen_entrant_lower_routing(self):
        rounds = generate_double_elimination(16, grand_final_policy="NO_RESET")
        lower = tuple(round_ for round_ in rounds if round_.section == "LOWER")

        self.assertEqual(
            lower,
            (
                self.round(
                    "LOWER",
                    1,
                    (LoserSlot(1, 1, "UPPER"), LoserSlot(1, 2, "UPPER")),
                    (LoserSlot(1, 3, "UPPER"), LoserSlot(1, 4, "UPPER")),
                    (LoserSlot(1, 5, "UPPER"), LoserSlot(1, 6, "UPPER")),
                    (LoserSlot(1, 7, "UPPER"), LoserSlot(1, 8, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    2,
                    (WinnerSlot(1, 1, "LOWER"), LoserSlot(2, 4, "UPPER")),
                    (WinnerSlot(1, 2, "LOWER"), LoserSlot(2, 3, "UPPER")),
                    (WinnerSlot(1, 3, "LOWER"), LoserSlot(2, 2, "UPPER")),
                    (WinnerSlot(1, 4, "LOWER"), LoserSlot(2, 1, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    3,
                    (WinnerSlot(2, 1, "LOWER"), WinnerSlot(2, 2, "LOWER")),
                    (WinnerSlot(2, 3, "LOWER"), WinnerSlot(2, 4, "LOWER")),
                ),
                self.round(
                    "LOWER",
                    4,
                    (WinnerSlot(3, 1, "LOWER"), LoserSlot(3, 2, "UPPER")),
                    (WinnerSlot(3, 2, "LOWER"), LoserSlot(3, 1, "UPPER")),
                ),
                self.round(
                    "LOWER",
                    5,
                    (WinnerSlot(4, 1, "LOWER"), WinnerSlot(4, 2, "LOWER")),
                ),
                self.round(
                    "LOWER",
                    6,
                    (WinnerSlot(5, 1, "LOWER"), LoserSlot(4, 1, "UPPER")),
                ),
            ),
        )

    def test_uneven_and_large_fields_are_complete_acyclic_and_unique(self):
        for entrant_count in (3, 5, 6, 9, 17, 256):
            with self.subTest(entrant_count=entrant_count):
                rounds = generate_double_elimination(
                    entrant_count, grand_final_policy="RESET"
                )
                field_size = 1 << (entrant_count - 1).bit_length()
                upper = tuple(r for r in rounds if r.section == "UPPER")
                lower = tuple(r for r in rounds if r.section == "LOWER")
                finals = tuple(r for r in rounds if r.section == "FINALS")

                self.assertEqual(len(upper), field_size.bit_length() - 1)
                self.assertEqual(
                    len(lower),
                    0 if field_size == 2 else 2 * (field_size.bit_length() - 1) - 2,
                )
                self.assertEqual(len(finals), 2)
                self.assertEqual(
                    sum(len(round_.matches) for round_ in rounds),
                    2 * field_size - 1,
                )
                seeds = {
                    slot.seed
                    for match in upper[0].matches
                    for slot in match.slots
                    if isinstance(slot, SeedSlot)
                }
                self.assertEqual(seeds, set(range(1, field_size + 1)))
                self.assertEqual(
                    seeds - set(range(1, entrant_count + 1)),
                    set(range(entrant_count + 1, field_size + 1)),
                )

                used_sources = []
                results = {}
                for round_ in rounds:
                    round_sources = []
                    active_entrants = []
                    for match in round_.matches:
                        entrants = []
                        for slot in match.slots:
                            if isinstance(slot, SeedSlot):
                                entrant = (
                                    slot.seed if slot.seed <= entrant_count else None
                                )
                            else:
                                source = (
                                    type(slot),
                                    slot.section,
                                    slot.round_number,
                                    slot.match_number,
                                )
                                used_sources.append(source)
                                round_sources.append(source)
                                if slot.section == round_.section:
                                    self.assertLess(slot.round_number, round_.number)
                                winner, loser = results[
                                    (slot.section, slot.round_number, slot.match_number)
                                ]
                                entrant = (
                                    winner if isinstance(slot, WinnerSlot) else loser
                                )
                            entrants.append(entrant)
                            if entrant is not None:
                                active_entrants.append(entrant)
                        present = [
                            entrant for entrant in entrants if entrant is not None
                        ]
                        results[(round_.section, round_.number, match.number)] = (
                            (min(present), max(present))
                            if len(present) == 2
                            else (present[0], None)
                            if present
                            else (None, None)
                        )
                    self.assertEqual(len(round_sources), len(set(round_sources)))
                    self.assertEqual(len(active_entrants), len(set(active_entrants)))
                self.assertEqual(len(used_sources), len(set(used_sources)))

    def test_full_fields_have_expected_match_counts_without_reset(self):
        for entrant_count in (2, 4, 8, 16):
            with self.subTest(entrant_count=entrant_count):
                rounds = generate_double_elimination(
                    entrant_count, grand_final_policy="NO_RESET"
                )
                self.assertEqual(
                    sum(len(round_.matches) for round_ in rounds),
                    2 * entrant_count - 2,
                )
                self.assertEqual(
                    len([round_ for round_ in rounds if round_.section == "FINALS"]),
                    1,
                )

    def test_rejects_invalid_fields_and_policies(self):
        for entrant_count in (1, 257):
            with self.subTest(entrant_count=entrant_count):
                with self.assertRaises(ValueError):
                    generate_double_elimination(
                        entrant_count, grand_final_policy="RESET"
                    )
        for policy in ("", "reset", "UNKNOWN"):
            with self.subTest(policy=policy):
                with self.assertRaises(ValueError):
                    generate_double_elimination(8, grand_final_policy=policy)
