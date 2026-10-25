from django.test import TestCase

from competitions import commands
from competitions.models import CompetitionEntrant, Match, StageEntry
from competitions.tests import test_double_elimination_commands as double_tests


class ResultProjectionTests(TestCase):
    setUp = double_tests.DoubleEliminationCommandTests.setUp
    _registration = double_tests.DoubleEliminationCommandTests._registration
    configure = double_tests.DoubleEliminationCommandTests.configure
    draw = double_tests.DoubleEliminationCommandTests.draw
    publish = double_tests.DoubleEliminationCommandTests.publish
    finish = double_tests.DoubleEliminationCommandTests.finish
    match = double_tests.DoubleEliminationCommandTests.match

    def withdraw(self, entry_id):
        entrant_id = StageEntry.objects.get(pk=entry_id).entrant_id
        CompetitionEntrant.objects.filter(pk=entrant_id).update(status="WITHDRAWN")
        return entrant_id

    def test_withdrawn_upper_loser_does_not_enter_lower_bracket(self):
        competition, draw = self.draw()
        upper = self.match(draw, "UPPER")
        self.withdraw(upper.slots.get(position=2).resolved_entry_id)
        self.finish(competition, upper, outcome="FORFEIT")
        lower = self.match(draw, "LOWER")
        self.assertTrue(lower.slots.get(position=1).is_resolved)
        self.assertIsNone(lower.slots.get(position=1).resolved_entry_id)
        self.assertEqual((lower.status, lower.outcome), ("PENDING", ""))

    def test_both_unavailable_real_sides_double_forfeit_with_partial_scores(self):
        _, draw = self.draw()
        upper = self.match(draw, "UPPER")
        for slot in upper.slots.all():
            self.withdraw(slot.resolved_entry_id)
        Match.objects.filter(pk=upper.pk).update(
            status="LIVE",
            side_one_score=1,
            side_two_score=0,
            applied_series_length=3,
            applied_series_mode="BEST_OF",
        )
        commands._resolve_automatic_matches(draw)
        upper.refresh_from_db()
        self.assertEqual((upper.status, upper.outcome), ("FINAL", "DOUBLE_FORFEIT"))
        self.assertEqual((upper.side_one_score, upper.side_two_score), (1, 0))
        self.assertEqual(upper.applied_series_length, 3)

    def test_inactive_historical_winner_does_not_advance_again(self):
        competition, draw = self.draw()
        upper = self.match(draw, "UPPER")
        self.finish(competition, upper)
        upper.refresh_from_db()
        original = (upper.outcome, upper.winner_id, upper.side_one_score)
        self.withdraw(upper.winner_id)
        commands._resolve_automatic_matches(draw)
        upper.refresh_from_db()
        self.assertEqual(
            (upper.outcome, upper.winner_id, upper.side_one_score), original
        )
        next_upper = self.match(draw, "UPPER", 2)
        self.assertIsNone(next_upper.slots.get(position=1).resolved_entry_id)
        self.assertEqual(next_upper.status, "PENDING")

    def test_two_source_updates_reset_one_coherent_final_and_clear_series(self):
        from competitions.result_projection import (
            project_elimination_results,
            apply_elimination_projection,
        )

        competition, draw = self.draw(4, policy="NO_RESET")
        first = self.match(draw, "UPPER", 1, 1)
        second = self.match(draw, "UPPER", 1, 2)
        self.finish(competition, first)
        self.finish(competition, second)
        upper_final = self.match(draw, "UPPER", 2)
        self.finish(competition, upper_final)
        upper_final.refresh_from_db()
        updated_winners = [
            m.slots.get(position=2).resolved_entry_id for m in (first, second)
        ]
        projection = project_elimination_results(
            draw,
            result_updates={
                m.pk: {
                    "status": "FINAL",
                    "outcome": "PLAYED",
                    "winner_id": winner,
                    "side_one_score": 0,
                    "side_two_score": 2,
                }
                for m, winner in zip((first, second), updated_winners)
            },
        )
        state = projection["matches"][upper_final.pk]
        self.assertEqual(
            state["slots"], [[True, updated_winners[0]], [True, updated_winners[1]]]
        )
        self.assertEqual(
            (state["status"], state["outcome"], state["winner_id"]),
            ("PENDING", "", None),
        )
        self.assertIn(upper_final.pk, projection["reset_match_ids"])
        apply_elimination_projection(draw, projection)
        upper_final.refresh_from_db()
        self.assertIsNone(upper_final.applied_series_length)
        self.assertEqual(upper_final.applied_series_mode, "")
        self.assertIsNone(upper_final.started_at)
        self.assertIsNone(upper_final.completed_at)

    def test_same_winner_score_update_preserves_played_descendants(self):
        from competitions.result_projection import project_elimination_results

        competition, draw = self.draw(4)
        first = self.match(draw, "UPPER", 1, 1)
        second = self.match(draw, "UPPER", 1, 2)
        self.finish(competition, first)
        self.finish(competition, second)
        final = self.match(draw, "UPPER", 2)
        self.finish(competition, final)
        first.refresh_from_db()
        projection = project_elimination_results(
            draw,
            result_updates={
                first.pk: {
                    "outcome": "PLAYED",
                    "winner_id": first.winner_id,
                    "side_one_score": 2,
                    "side_two_score": 1,
                }
            },
        )
        self.assertEqual(projection["changed_match_ids"], [first.pk])
        self.assertEqual(projection["reset_match_ids"], [])
        self.assertEqual(projection["matches"][final.pk]["status"], "FINAL")

    def test_status_overrides_preserve_all_entered_finals_for_both_policies(self):
        from competitions.result_projection import project_elimination_results
        from django.db import transaction

        for policy in ("RESET", "NO_RESET"):
            with self.subTest(policy=policy), transaction.atomic():
                competition, draw = self.draw(2, policy=policy)
                self.finish(competition, self.match(draw, "UPPER"))
                final = self.match(draw, "FINALS")
                self.finish(competition, final, position=2)
                if policy == "RESET":
                    self.finish(competition, self.match(draw, "FINALS", 2))
                before = {
                    m.pk: (m.winner_id, m.outcome, m.side_one_score, m.completed_at)
                    for m in Match.objects.filter(round__draw=draw, status="FINAL")
                }
                overrides = dict(
                    draw.entries.values_list("entrant_id", "entrant__status")
                )
                overrides = {pk: "WITHDRAWN" for pk in overrides}
                projection = project_elimination_results(
                    draw, result_updates={}, entrant_statuses=overrides
                )
                for pk, expected in before.items():
                    state = projection["matches"][pk]
                    self.assertEqual(
                        (
                            state["winner_id"],
                            state["outcome"],
                            state["side_one_score"],
                            state["completed_at"],
                        ),
                        expected,
                    )
                self.assertEqual(projection["changed_match_ids"], [])
                transaction.set_rollback(True)

    def test_pending_real_fixture_forfeits_and_unresolved_routes_wait(self):
        from competitions.result_projection import (
            project_elimination_results,
            apply_elimination_projection,
        )

        _, draw = self.draw(4)
        first = self.match(draw, "UPPER")
        removed = first.slots.get(position=2).resolved_entry
        projection = project_elimination_results(
            draw,
            result_updates={},
            entrant_statuses={removed.entrant_id: "DISQUALIFIED"},
        )
        self.assertEqual(projection["matches"][first.pk]["outcome"], "FORFEIT")
        lower = self.match(draw, "LOWER")
        self.assertEqual(projection["matches"][lower.pk]["status"], "PENDING")
        self.assertEqual(projection["matches"][lower.pk]["outcome"], "")
        self.assertEqual(
            projection["matches"][lower.pk]["slots"], [[True, None], [False, None]]
        )
        apply_elimination_projection(draw, projection)
        removed.entrant.refresh_from_db()
        self.assertEqual(removed.entrant.status, "ACTIVE")

    def test_structural_byes_keep_existing_empty_route_semantics(self):
        from competitions.result_projection import project_elimination_results

        _, draw = self.draw(3)
        byes = list(Match.objects.filter(round__draw=draw, outcome="BYE"))
        self.assertTrue(byes)
        projection = project_elimination_results(draw, result_updates={})
        self.assertEqual(projection["changed_match_ids"], [])
        for bye in byes:
            self.assertEqual(projection["matches"][bye.pk]["outcome"], "BYE")

    def test_routed_live_fixture_keeps_partial_scores_on_removal_forfeit(self):
        from competitions.result_projection import (
            project_elimination_results,
            apply_elimination_projection,
        )

        competition, draw = self.draw(4)
        self.finish(competition, self.match(draw, "UPPER", 1, 1))
        self.finish(competition, self.match(draw, "UPPER", 1, 2))
        final = self.match(draw, "UPPER", 2)
        removed = final.slots.get(position=2).resolved_entry
        Match.objects.filter(pk=final.pk).update(
            status="LIVE",
            side_one_score=1,
            side_two_score=0,
            applied_series_length=3,
            applied_series_mode="BEST_OF",
        )
        projection = project_elimination_results(
            draw, result_updates={}, entrant_statuses={removed.entrant_id: "WITHDRAWN"}
        )
        self.assertNotIn(final.pk, projection["reset_match_ids"])
        apply_elimination_projection(draw, projection)
        final.refresh_from_db()
        self.assertEqual(final.outcome, "FORFEIT")
        self.assertEqual((final.side_one_score, final.side_two_score), (1, 0))
        self.assertEqual(
            (final.applied_series_length, final.applied_series_mode), (3, "BEST_OF")
        )
