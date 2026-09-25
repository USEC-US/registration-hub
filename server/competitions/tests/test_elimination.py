from django.test import SimpleTestCase

from competitions.elimination import (
    SeedSlot,
    WinnerSlot,
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
