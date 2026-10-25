from dataclasses import asdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from competitions import commands, swiss_commands
from competitions.models import CompetitionEntrant, Match
from competitions.qualification import stage_qualification
from competitions.swiss import pair_swiss_round, rank_swiss, SwissResult
from competitions.swiss_corrections import project_swiss_correction
from competitions.tests import test_swiss_commands as fixtures
from competitions.tests import test_round_robin_commands as rr_fixtures


class AvailabilityPairingTests(SimpleTestCase):
    def test_unavailable_entry_keeps_history_and_saved_seed_folding(self):
        seeds = {1: 5, 2: 1, 3: 4, 4: 2, 5: 3}
        results = [SwissResult(1, 1, 2, 3, "PLAYED", 2, 0, 2)]
        rows = rank_swiss(
            seeds,
            results,
            format="SWISS_FIXED",
            points=(Decimal(3), Decimal(1), Decimal(0)),
            tiebreaks=["OPPONENT_POINTS"],
        )
        before = [asdict(row) for row in rows]
        pairing = pair_swiss_round(
            seeds, rows, results, format="SWISS_FIXED", unavailable_entry_ids={2}
        )
        self.assertEqual({i for pair in pairing.pairs for i in pair}, {1, 3, 4, 5})
        self.assertIsNone(pairing.bye_entry_id)
        self.assertEqual([asdict(row) for row in rows], before)
        self.assertEqual(next(r for r in rows if r.entry_id == 3).opponent_points, 3)
        folded = pair_swiss_round(
            seeds,
            rank_swiss(
                seeds,
                [],
                format="SWISS_FIXED",
                points=(Decimal(3), Decimal(1), Decimal(0)),
                tiebreaks=[],
            ),
            [],
            format="SWISS_FIXED",
            unavailable_entry_ids={2},
        )
        self.assertEqual(folded.pairs, ((4, 1), (5, 3)))

    def test_unavailability_does_not_relax_rematch_policy(self):
        seeds = {i: i for i in range(1, 6)}
        results = [SwissResult(1, 1, 2, 3, "PLAYED", 2, 0, 2)]
        rows = rank_swiss(
            seeds,
            results,
            format="SWISS_FIXED",
            points=(Decimal(3), Decimal(1), Decimal(0)),
            tiebreaks=[],
        )
        with self.assertRaises(ValueError):
            pair_swiss_round(
                seeds,
                rows,
                results,
                format="SWISS_FIXED",
                unavailable_entry_ids={1, 4, 5},
            )
        pairing = pair_swiss_round(
            seeds,
            rows,
            results,
            format="SWISS_FIXED",
            unavailable_entry_ids={1, 4, 5},
            allow_rematches=True,
        )
        self.assertEqual(pairing.repeat_pairs, ((2, 3),))


class LifecycleSwissTests(TestCase):
    setUp = fixtures.SwissCommandTests.setUp
    _registration = fixtures.SwissCommandTests._registration
    _competition = fixtures.SwissCommandTests._competition
    _swiss = fixtures.SwissCommandTests._swiss
    _elimination = fixtures.SwissCommandTests._elimination
    _revision = fixtures.SwissCommandTests._revision
    _draw = fixtures.SwissCommandTests._draw
    _finish = fixtures.SwissCommandTests._finish
    _generate = fixtures.SwissCommandTests._generate
    _publish = fixtures.SwissCommandTests._publish

    def test_removal_preserves_history_invalidates_private_round_and_regenerates(self):
        draw = self._draw(5)
        first = draw.rounds.get()
        self._finish(first)
        second = self._generate()
        self._publish(second)
        self._finish(second)
        private = self._generate(allow_rematches=True, internal_reason="Needed")
        before = [asdict(row) for row in swiss_commands.swiss_standings(draw)]
        entry = draw.entries.order_by("seed").first()
        CompetitionEntrant.objects.filter(pk=entry.entrant_id).update(
            status="WITHDRAWN"
        )
        for old in (first, second):
            old.refresh_from_db()
            swiss_commands.validate_swiss_round(old)
        with self.assertRaises(ValidationError):
            swiss_commands.validate_swiss_round(private)
        impact = project_swiss_correction(draw, projected_matches=None)
        self.assertEqual(impact["retired_round_ids"], [private.pk])
        replacement = self._generate(
            regenerate=True, allow_rematches=True, internal_reason="Needed"
        )
        self.assertFalse(replacement.matches.filter(slots__entry=entry).exists())
        self.assertEqual(draw.swiss_round_limit, 3)
        self.assertEqual(
            [asdict(row) for row in swiss_commands.swiss_standings(draw)], before
        )
        restoration = project_swiss_correction(
            draw,
            projected_matches=None,
            entrant_statuses={entry.entrant_id: "ACTIVE"},
            retire_from_round=3,
        )
        self.assertEqual(restoration["retired_round_ids"], [replacement.pk])
        match = first.matches.filter(outcome="PLAYED").first()
        changed = {
            match.pk: dict(
                status="FINAL",
                outcome="PLAYED",
                side_one_score=0,
                side_two_score=2,
                winner_id=match.slots.get(position=2).entry_id,
            )
        }
        correction = project_swiss_correction(draw, projected_matches=changed)
        self.assertEqual(correction["retired_round_ids"], [second.pk, replacement.pk])

    def test_removed_unapproved_registration_does_not_block_active_peers(self):
        draw = self._draw(5)
        self._finish(draw.rounds.get())
        entry = draw.entries.first()
        registration = entry.entrant.registration
        registration.status = "REJECTED"
        registration.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self._generate()
        CompetitionEntrant.objects.filter(pk=entry.entrant_id).update(
            status="WITHDRAWN"
        )
        next_round = self._generate()
        self.assertFalse(next_round.matches.filter(slots__entry=entry).exists())
        self._publish(next_round)

    def test_earned_top_two_is_not_replaced_by_third_finisher(self):
        draw = self._draw(4, round_count=2)
        self._finish(draw.rounds.get())
        final = self._generate()
        self._publish(final)
        for match in final.matches.order_by("number"):
            commands.finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self._revision(),
                outcome="PLAYED",
                side_one_score=2,
                side_two_score=0 if match.number == 1 else 1,
            )
        state = stage_qualification(draw)
        self.assertEqual(state["cutoffs"], [])
        first, second = [draw.entries.get(pk=i) for i in state["qualifier_entry_ids"]]
        third = next(
            e for e in draw.entries.all() if e.pk not in state["qualifier_entry_ids"]
        )
        projected = stage_qualification(
            draw, entrant_statuses={second.entrant_id: "WITHDRAWN"}
        )
        self.assertEqual(projected["earned_qualifier_entry_ids"], [first.pk, second.pk])
        self.assertEqual(projected["qualifier_entry_ids"], [first.pk])
        self.assertEqual(projected["qualification_state"], "BLOCKED")
        self.assertNotIn(third.pk, projected["qualifier_entry_ids"])
        from competitions.handoff_commands import generate_next_stage_draw

        CompetitionEntrant.objects.filter(pk=second.entrant_id).update(
            status="WITHDRAWN"
        )
        with self.assertRaisesMessage(ValidationError, "unavailable"):
            generate_next_stage_draw(
                actor=self.actor,
                stage_id=self.competition.stages.get(sequence=2).pk,
                expected_revision=self._revision(),
            )

    def test_threshold_completion_ignores_inactive_continuers_preserving_records(self):
        draw = self._draw(
            4,
            format="SWISS_THRESHOLD",
            advancement_count=None,
            win_target=1,
            loss_limit=2,
        )
        self._finish(draw.rounds.get())
        rows = swiss_commands.swiss_standings(draw)
        before = [asdict(row) for row in rows]
        losers = {row.entry_id for row in rows if row.status == "ACTIVE"}
        statuses = {
            entry.entrant_id: "WITHDRAWN"
            for entry in draw.entries.all()
            if entry.pk in losers
        }
        self.assertEqual(
            stage_qualification(draw)["qualification_state"], "PROVISIONAL"
        )
        state = stage_qualification(draw, entrant_statuses=statuses)
        self.assertEqual(state["qualification_state"], "RESOLVED")
        self.assertEqual(
            set(state["qualifier_entry_ids"]),
            {r.entry_id for r in rows if r.status == "QUALIFIED"},
        )
        self.assertEqual(
            [asdict(row) for row in swiss_commands.swiss_standings(draw)], before
        )
        swiss_commands.update_swiss_completion(
            self.stage, draw, entrant_statuses=statuses
        )
        self.stage.refresh_from_db()
        self.assertEqual(self.stage.status, "COMPLETE")


class LifecycleQualificationTests(TestCase):
    setUp = rr_fixtures.RoundRobinCommandTests.setUp
    _registration = rr_fixtures.RoundRobinCommandTests._registration
    configure = rr_fixtures.RoundRobinCommandTests.configure
    setup_stage = rr_fixtures.RoundRobinCommandTests.setup_stage
    choose = rr_fixtures.RoundRobinCommandTests.choose
    draw = rr_fixtures.RoundRobinCommandTests.draw
    publish = rr_fixtures.RoundRobinCommandTests.publish
    result = rr_fixtures.RoundRobinCommandTests.result

    def _group(self, *, tied=False):
        self.configure(tiebreaks=())
        self.choose(size=4)
        draw = self.draw(group_specs=[("A", 2)])
        self.publish()
        for match in Match.objects.filter(round__draw=draw).prefetch_related("slots"):
            one, two = [slot.entry_id for slot in match.slots.all()]
            self.result(
                match,
                side_one_score=1 if tied else 2 * (one < two),
                side_two_score=1 if tied else 2 * (one > two),
            )
        return draw, draw.groups.get()

    def test_group_and_stage_keep_earned_places_and_block_shortfall(self):
        from competitions.round_robin_commands import (
            group_standings,
            update_round_robin_completion,
        )

        draw, group = self._group()
        initial = stage_qualification(draw)
        first, second = [draw.entries.get(pk=i) for i in initial["qualifier_entry_ids"]]
        statuses = {second.entrant_id: "WITHDRAWN"}
        projected = stage_qualification(draw, entrant_statuses=statuses)
        self.assertEqual(projected["earned_qualifier_entry_ids"], [first.pk, second.pk])
        self.assertEqual(projected["qualifier_entry_ids"], [first.pk])
        self.assertEqual(projected["qualification_state"], "BLOCKED")
        self.assertNotEqual(initial["fingerprint"], projected["fingerprint"])
        CompetitionEntrant.objects.filter(pk=second.entrant_id).update(
            status="WITHDRAWN"
        )
        state = group_standings(group)
        self.assertEqual(state["earned_qualifiers"], [first.pk, second.pk])
        self.assertEqual(state["qualifiers"], [first.pk])
        self.assertEqual(state["qualification_state"], "BLOCKED")
        self.assertTrue(state["block_reason"])
        self.assertEqual(stage_qualification(draw)["qualification_state"], "BLOCKED")
        update_round_robin_completion(draw)
        draw.stage.refresh_from_db()
        self.assertEqual(draw.stage.status, "AWAITING")

    def test_inactive_cutoff_contender_cannot_win_new_resolution(self):
        from competitions.qualification import preview_qualification_tie

        draw, group = self._group(tied=True)
        initial = stage_qualification(draw)
        tie = initial["cutoffs"][0]
        entry = draw.entries.get(pk=tie["entry_ids"][0])
        CompetitionEntrant.objects.filter(pk=entry.entrant_id).update(
            status="WITHDRAWN"
        )
        self.assertEqual(stage_qualification(draw)["qualification_state"], "BLOCKED")
        self.competition.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "active and approved"):
            preview_qualification_tie(
                actor=self.actor,
                draw_id=draw.pk,
                group_id=group.pk,
                expected_revision=self.competition.revision,
                tied_entry_ids=tie["entry_ids"],
                ordered_entry_ids=tie["entry_ids"],
                method="MANUAL",
            )

    def _remove_with_earned_decisions(self, draw, entry):
        from competitions.models import ChangeSet, Competition

        state = stage_qualification(draw)
        self.competition.refresh_from_db()
        revision = self.competition.revision + 1
        change = ChangeSet.objects.create(
            competition=self.competition,
            revision=revision,
            kind="entrant_withdrawn",
            actor=self.actor,
            private_data={
                "entrant_id": entry.entrant_id,
                "earned_resolution_ids": state["earned_resolution_ids"],
            },
        )
        Competition.objects.filter(pk=self.competition.pk).update(revision=revision)
        CompetitionEntrant.objects.filter(pk=entry.entrant_id).update(
            status="WITHDRAWN", removal_change=change
        )
        return change

    def test_resolved_tie_keeps_earned_winner_after_lifecycle_supersedes_decision(self):
        from competitions.models import TieResolution
        from competitions.qualification import (
            preview_qualification_tie,
            confirm_qualification_tie,
        )
        from competitions.round_robin_commands import group_standings

        draw, group = self._group(tied=True)
        tie = stage_qualification(draw)["cutoffs"][0]
        self.competition.refresh_from_db()
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=draw.pk,
            group_id=group.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=tie["entry_ids"],
            ordered_entry_ids=tie["entry_ids"],
            method="MANUAL",
        )
        resolution = confirm_qualification_tie(
            actor=self.actor, token=preview["token"], internal_reason="Decision"
        )
        winner = draw.entries.get(pk=tie["entry_ids"][0])
        expected_earned = tie["entry_ids"][:2]
        removal = self._remove_with_earned_decisions(draw, winner)
        for superseded in (False, True):
            if superseded:
                TieResolution.objects.filter(pk=resolution.pk).update(
                    state="SUPERSEDED"
                )
            state = stage_qualification(draw)
            self.assertEqual(state["earned_qualifier_entry_ids"], expected_earned)
            self.assertEqual(state["qualifier_entry_ids"], expected_earned[1:])
            self.assertEqual(state["qualification_state"], "BLOCKED")
            self.assertNotIn(resolution.pk, state["resolution_states"])
            self.assertEqual(state["earned_resolution_ids"], [resolution.pk])
            self.assertEqual(group_standings(group)["qualification_state"], "BLOCKED")

        CompetitionEntrant.objects.filter(pk=winner.entrant_id).update(
            removal_change=None
        )
        without_provenance = stage_qualification(draw)
        self.assertEqual(without_provenance["earned_qualifier_entry_ids"], [])
        self.assertEqual(without_provenance["earned_resolution_ids"], [])
        CompetitionEntrant.objects.filter(pk=winner.entrant_id).update(
            removal_change=removal
        )
        self.assertEqual(
            stage_qualification(draw)["earned_resolution_ids"], [resolution.pk]
        )

    def test_retired_extra_contests_still_establish_earned_places(self):
        from competitions.models import TieResolution, Round
        from competitions.qualification import (
            preview_qualification_tie,
            confirm_qualification_tie,
        )

        draw, group = self._group(tied=True)
        tie = stage_qualification(draw)["cutoffs"][0]
        self.competition.refresh_from_db()
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=draw.pk,
            group_id=group.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=tie["entry_ids"],
            method="EXTRA_MATCHES",
            series_length=3,
        )
        resolution = confirm_qualification_tie(actor=self.actor, token=preview["token"])
        for match in Match.objects.filter(
            round__tie_resolution=resolution
        ).prefetch_related("slots"):
            one, two = [slot.entry_id for slot in match.slots.all()]
            self.result(
                match, side_one_score=2 * (one < two), side_two_score=2 * (one > two)
            )
        before = stage_qualification(draw)
        winner = draw.entries.get(pk=before["qualifier_entry_ids"][0])
        self._remove_with_earned_decisions(draw, winner)
        TieResolution.objects.filter(pk=resolution.pk).update(state="SUPERSEDED")
        Round.objects.filter(tie_resolution=resolution).update(state="SUPERSEDED")
        after = stage_qualification(draw)
        self.assertEqual(
            after["earned_qualifier_entry_ids"], before["qualifier_entry_ids"]
        )
        self.assertEqual(
            after["qualifier_entry_ids"], before["qualifier_entry_ids"][1:]
        )
        self.assertEqual(after["qualification_state"], "BLOCKED")
        self.assertEqual(after["resolution_states"], {})
        self.assertEqual(after["earned_resolution_ids"], [resolution.pk])

    def test_score_reversal_then_withdrawal_cannot_revive_discarded_decision(self):
        from competitions.models import TieResolution
        from competitions.qualification import (
            preview_qualification_tie,
            confirm_qualification_tie,
        )

        draw, group = self._group(tied=True)
        tie = stage_qualification(draw)["cutoffs"][0]
        self.competition.refresh_from_db()
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=draw.pk,
            group_id=group.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=tie["entry_ids"],
            ordered_entry_ids=tie["entry_ids"],
            method="MANUAL",
        )
        resolution = confirm_qualification_tie(
            actor=self.actor, token=preview["token"], internal_reason="Decision"
        )
        match = Match.objects.filter(
            round__group=group, round__section="NORMAL"
        ).first()
        for one, two in ((2, 0), (1, 1)):
            self.competition.refresh_from_db()
            correction = commands.preview_correction(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self.competition.revision,
                outcome="PLAYED",
                side_one_score=one,
                side_two_score=two,
            )
            commands.apply_correction(
                actor=self.actor,
                token=correction["token"],
                internal_reason="Independent correction",
            )
        resolution.refresh_from_db()
        self.assertEqual(resolution.state, TieResolution.State.SUPERSEDED)
        self.assertEqual(
            stage_qualification(draw)["qualification_state"], "AWAITING_RESOLUTION"
        )
        winner = draw.entries.get(pk=tie["entry_ids"][0])
        change = self._remove_with_earned_decisions(draw, winner)
        self.assertEqual(change.private_data["earned_resolution_ids"], [])
        after = stage_qualification(draw)
        self.assertEqual(after["earned_qualifier_entry_ids"], [])
        self.assertEqual(after["qualifier_entry_ids"], [])
        self.assertEqual(after["qualification_state"], "BLOCKED")

    def test_two_removals_retain_authoritative_history_after_first_restores(self):
        from competitions.models import TieResolution
        from competitions.qualification import (
            preview_qualification_tie,
            confirm_qualification_tie,
        )
        from competitions.serializers import PublicStageSerializer
        import json

        draw, group = self._group(tied=True)
        tie = stage_qualification(draw)["cutoffs"][0]
        self.competition.refresh_from_db()
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=draw.pk,
            group_id=group.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=tie["entry_ids"],
            ordered_entry_ids=tie["entry_ids"],
            method="MANUAL",
        )
        resolution = confirm_qualification_tie(
            actor=self.actor, token=preview["token"], internal_reason="Decision"
        )
        first, second = [draw.entries.get(pk=i) for i in tie["entry_ids"][:2]]
        self._remove_with_earned_decisions(draw, first)
        TieResolution.objects.filter(pk=resolution.pk).update(state="SUPERSEDED")
        second_removal = self._remove_with_earned_decisions(draw, second)
        self.assertEqual(
            second_removal.private_data["earned_resolution_ids"], [resolution.pk]
        )
        CompetitionEntrant.objects.filter(pk=first.entrant_id).update(
            status="ACTIVE", removal_change=None
        )
        # Relabeling an existing removal does not replace its original authority.
        CompetitionEntrant.objects.filter(pk=second.entrant_id).update(
            status="DISQUALIFIED"
        )
        after = stage_qualification(draw)
        self.assertEqual(after["earned_qualifier_entry_ids"], [first.pk, second.pk])
        self.assertEqual(after["qualifier_entry_ids"], [first.pk])
        self.assertEqual(after["qualification_state"], "BLOCKED")
        self.assertEqual(after["earned_resolution_ids"], [resolution.pk])
        self.assertNotIn(
            "earned_resolution_ids", json.dumps(PublicStageSerializer(draw.stage).data)
        )


class RemovalDecisionProvenanceTests(SimpleTestCase):
    def test_only_subject_owned_removal_events_authorize_history(self):
        from types import SimpleNamespace
        from competitions.qualification import historical_resolution_entries

        change = SimpleNamespace(
            competition_id=1,
            kind="entrant_withdrawn",
            private_data={"entrant_id": 2, "earned_resolution_ids": [9]},
        )
        entrant = SimpleNamespace(
            pk=2,
            competition_id=1,
            status="WITHDRAWN",
            removal_change_id=7,
            removal_change=change,
        )
        entry = SimpleNamespace(pk=3, entrant=entrant)
        self.assertEqual(historical_resolution_entries([entry]), {9: {3}})
        for invalid in (
            dict(competition_id=99),
            dict(kind="result_corrected"),
            dict(private_data={"entrant_id": 99, "earned_resolution_ids": [9]}),
            dict(private_data={"entrant_id": True, "earned_resolution_ids": [9]}),
            dict(private_data={"entrant_id": 2, "earned_resolution_ids": [True]}),
            dict(private_data={"entrant_id": 2, "earned_resolution_ids": "9"}),
            dict(private_data=[]),
        ):
            with self.subTest(invalid=invalid):
                changed = SimpleNamespace(**(vars(change) | invalid))
                altered = SimpleNamespace(
                    **(vars(entrant) | {"removal_change": changed})
                )
                self.assertEqual(
                    historical_resolution_entries(
                        [SimpleNamespace(pk=3, entrant=altered)]
                    ),
                    {},
                )
        self.assertEqual(
            historical_resolution_entries([entry], entrant_statuses={2: "ACTIVE"}), {}
        )
        entrant.removal_change_id = None
        self.assertEqual(historical_resolution_entries([entry]), {})
