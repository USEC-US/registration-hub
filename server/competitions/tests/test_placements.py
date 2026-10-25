from django.test import SimpleTestCase

from competitions import elimination


class PlacementTests(SimpleTestCase):
    def result(
        self, number, section, one, two, winner, outcome="PLAYED", status="FINAL"
    ):
        return elimination.EliminationResult(
            number, section, status, outcome, one, two, winner
        )

    def test_two_entry_single_finishing_bands(self):
        table = elimination.finishing_bands(
            [11, 12],
            [self.result(1, "NORMAL", 11, 12, 11)],
            format="SINGLE_ELIMINATION",
        )
        self.assertEqual(table.bands, ((11,), (12,)))
        self.assertEqual(table.unranked_entry_ids, ())

    def test_single_bands_follow_terminal_round_not_win_totals(self):
        results = [
            self.result(1, "NORMAL", 1, 8, 1),
            self.result(1, "NORMAL", 4, 5, 4),
            self.result(1, "NORMAL", 2, 7, 2),
            self.result(1, "NORMAL", 3, 6, 3),
            self.result(2, "NORMAL", 1, 4, 1),
            self.result(2, "NORMAL", 2, 3, 2),
            self.result(3, "NORMAL", 1, 2, 1),
        ]
        table = elimination.finishing_bands(
            range(1, 9), results, format="SINGLE_ELIMINATION"
        )
        self.assertEqual(table.bands, ((1,), (2,), (3, 4), (5, 6, 7, 8)))

    def test_double_uses_deciding_reset_and_lower_exit_depth(self):
        results = [
            self.result(1, "LOWER", 3, 4, 3),
            self.result(2, "LOWER", 2, 3, 2),
            self.result(1, "FINALS", 1, 2, 2),
            self.result(2, "FINALS", 1, 2, 1),
        ]
        table = elimination.finishing_bands(
            [1, 2, 3, 4], results, format="DOUBLE_ELIMINATION"
        )
        self.assertEqual(table.bands, ((1,), (2,), (3,), (4,)))
        results[-1] = self.result(2, "FINALS", None, None, None, status="NOT_REQUIRED")
        self.assertEqual(
            elimination.finishing_bands(
                [1, 2, 3, 4], results, format="DOUBLE_ELIMINATION"
            ).bands,
            ((2,), (1,), (3,), (4,)),
        )

    def test_double_forfeit_has_no_invented_champion_or_upper_placement(self):
        results = [
            self.result(1, "UPPER", 3, 4, None, "DOUBLE_FORFEIT"),
            self.result(1, "FINALS", 1, 2, None, "DOUBLE_FORFEIT"),
        ]
        table = elimination.finishing_bands(
            [1, 2, 3, 4], results, format="DOUBLE_ELIMINATION"
        )
        self.assertEqual(table.bands, ((1, 2),))
        self.assertEqual(table.unranked_entry_ids, (3, 4))

    def test_byes_and_lower_double_forfeits_only_rank_real_entries(self):
        results = [
            self.result(1, "UPPER", 1, None, 1, "BYE"),
            self.result(1, "LOWER", 3, 4, None, "DOUBLE_FORFEIT"),
            self.result(1, "FINALS", 1, 2, 1, "FORFEIT"),
        ]
        self.assertEqual(
            elimination.finishing_bands(
                [1, 2, 3, 4], results, format="DOUBLE_ELIMINATION"
            ).bands,
            ((1,), (2,), (3, 4)),
        )
