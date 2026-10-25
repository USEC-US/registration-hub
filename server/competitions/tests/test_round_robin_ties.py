from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from competitions.commands import apply_correction, preview_correction, start_match
from competitions.models import Match, Stage, TieResolution
from competitions.round_robin_commands import (
    confirm_group_tie,
    group_standings,
    preview_group_tie,
)
from competitions.tests import test_round_robin_commands as fixtures


class RoundRobinTieTests(TestCase):
    setUp = fixtures.RoundRobinCommandTests.setUp
    _registration = fixtures.RoundRobinCommandTests._registration
    configure = fixtures.RoundRobinCommandTests.configure
    setup_stage = fixtures.RoundRobinCommandTests.setup_stage
    choose = fixtures.RoundRobinCommandTests.choose
    draw = fixtures.RoundRobinCommandTests.draw
    publish = fixtures.RoundRobinCommandTests.publish
    published_group = fixtures.RoundRobinCommandTests.published_group
    result = fixtures.RoundRobinCommandTests.result

    def tied_group(self, **rules):
        self.saved = self.published_group(tiebreaks=rules.pop("tiebreaks", ()), **rules)
        self.group = self.saved.groups.get()
        for match in Match.objects.filter(round__draw=self.saved):
            self.result(match)
        return list(self.group.entries.values_list("pk", flat=True))

    def preview(self, method="MANUAL", parent=None, **overrides):
        self.competition.refresh_from_db()
        tie = group_standings(self.group)["cutoff_ties"][0]
        return preview_group_tie(
            actor=self.actor,
            group_id=self.group.pk,
            expected_revision=self.competition.revision,
            **{
                "tied_entry_ids": tie["entry_ids"],
                "method": method,
                "ordered_entry_ids": list(reversed(tie["entry_ids"]))
                if method == "MANUAL"
                else [],
                "parent_resolution_id": parent,
                **overrides,
            },
        )

    def confirm(self, preview, reason="Internal organizer decision"):
        return confirm_group_tie(
            actor=self.actor, token=preview["token"], internal_reason=reason
        )

    def test_manual_decision_selects_only_tied_entrants_and_preserves_points(self):
        ids = self.tied_group()
        preview = self.preview()
        resolution = self.confirm(preview)
        self.assertEqual(resolution.decision_order, list(reversed(ids)))
        self.assertEqual(group_standings(self.group)["qualifiers"], [ids[-1]])
        self.assertEqual(
            [row.points for row in group_standings(self.group)["standings"]], [2, 2, 2]
        )
        self.saved.stage.refresh_from_db()
        self.assertEqual(self.saved.stage.status, Stage.Status.COMPLETE)
        with self.assertRaises(ValidationError):
            self.confirm(preview)

    def test_invalid_manual_order_and_missing_reason_are_rejected(self):
        ids = self.tied_group()
        for order in ([ids[0]] * 3, ids[:2], [*ids[:2], 999999]):
            with self.subTest(order=order), self.assertRaises(ValidationError):
                self.preview(ordered_entry_ids=order)
        preview = self.preview()
        with self.assertRaises(ValidationError):
            self.confirm(preview, reason="")
        self.assertFalse(TieResolution.objects.exists())

    def test_extra_mini_table_uses_decisive_matches_and_no_original_points(self):
        ids = self.tied_group()
        resolution = self.confirm(self.preview(method="EXTRA_MATCHES", series_length=3))
        matches = list(
            Match.objects.filter(round__tie_resolution=resolution).prefetch_related(
                "slots"
            )
        )
        self.assertEqual(len(matches), 3)
        for match in matches:
            self.assertEqual(match.effective_series_mode, "BEST_OF")
            first, second = [slot.entry_id for slot in match.slots.all()]
            self.result(
                match,
                side_one_score=2 if ids.index(first) < ids.index(second) else 0,
                side_two_score=0 if ids.index(first) < ids.index(second) else 2,
            )
        resolution.refresh_from_db()
        self.assertEqual(resolution.state, TieResolution.State.CONFIRMED)
        self.assertEqual(group_standings(self.group)["qualifiers"], [ids[0]])
        self.assertEqual(
            [row.points for row in group_standings(self.group)["standings"]], [2, 2, 2]
        )

    def test_start_extra_contest_persists_decisive_mode(self):
        self.tied_group()
        resolution = self.confirm(self.preview(method="EXTRA_MATCHES", series_length=3))
        match = Match.objects.filter(round__tie_resolution=resolution).first()
        self.competition.refresh_from_db()
        start_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self.competition.revision,
        )
        match.refresh_from_db()
        self.assertEqual(
            (match.applied_series_mode, match.applied_series_length), ("BEST_OF", 3)
        )

    def test_remaining_mini_table_tie_requires_explicit_nested_resolution(self):
        ids = self.tied_group()
        resolution = self.confirm(self.preview(method="EXTRA_MATCHES"))
        cyclic = {(ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])}
        for match in Match.objects.filter(
            round__tie_resolution=resolution
        ).prefetch_related("slots"):
            first, second = [slot.entry_id for slot in match.slots.all()]
            self.result(
                match,
                side_one_score=int((first, second) in cyclic),
                side_two_score=int((second, first) in cyclic),
            )
        resolution.refresh_from_db()
        self.assertEqual(resolution.state, TieResolution.State.AWAITING_RESOLUTION)
        self.assertEqual(
            group_standings(self.group)["qualification_state"], "AWAITING_RESOLUTION"
        )
        self.confirm(self.preview(parent=resolution.pk))
        resolution.refresh_from_db()
        self.assertEqual(resolution.state, TieResolution.State.CONFIRMED)
        self.assertEqual(group_standings(self.group)["qualifiers"], [ids[-1]])

    def test_repeat_stale_and_even_length_extra_choices_are_rejected(self):
        self.tied_group()
        with self.assertRaises(ValidationError):
            self.preview(method="EXTRA_MATCHES", series_length=2)
        preview = self.preview(method="EXTRA_MATCHES")
        self.confirm(preview)
        with self.assertRaises(ValidationError):
            self.confirm(preview)
        with self.assertRaises(ValidationError):
            self.preview(method="EXTRA_MATCHES")

    def test_same_winner_score_correction_invalidates_tie(self):
        self.saved = self.published_group(
            series_mode="BEST_OF",
            default_series_length=3,
            tiebreaks=("GAME_DIFFERENCE",),
        )
        self.group = self.saved.groups.get()
        ids = list(self.group.entries.values_list("pk", flat=True))
        cyclic = {(ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])}
        matches = list(
            Match.objects.filter(round__draw=self.saved).prefetch_related("slots")
        )
        for match in matches:
            first, second = [slot.entry_id for slot in match.slots.all()]
            self.result(
                match,
                side_one_score=2 * int((first, second) in cyclic),
                side_two_score=2 * int((second, first) in cyclic),
            )
        resolution = self.confirm(self.preview(method="EXTRA_MATCHES"))
        extra = Match.objects.filter(round__tie_resolution=resolution).first()
        self.result(extra, side_one_score=1, side_two_score=0)
        target = matches[0]
        target.refresh_from_db()
        self.competition.refresh_from_db()
        # Keep the same winner while changing only its opponent's score.
        preview = preview_correction(
            actor=self.actor,
            match_id=target.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2 if target.side_one_score == 2 else 1,
            side_two_score=1 if target.side_one_score == 2 else 2,
        )
        self.assertIn(
            resolution.pk, preview["group_impact"]["invalidated_resolution_ids"]
        )
        apply_correction(
            actor=self.actor, token=preview["token"], internal_reason="Score typo"
        )
        resolution.refresh_from_db()
        extra.refresh_from_db()
        self.assertEqual(resolution.state, TieResolution.State.SUPERSEDED)
        self.assertEqual(extra.status, Match.Status.FINAL)
        self.competition.refresh_from_db()
        other_extra = Match.objects.filter(
            round__tie_resolution=resolution, started_at__isnull=True
        ).first()
        with self.assertRaises(ValidationError):
            start_match(
                actor=self.actor,
                match_id=other_extra.pk,
                expected_revision=self.competition.revision,
            )
        self.assertEqual(
            Match.objects.filter(
                pk__in=[match.pk for match in matches], status="FINAL"
            ).count(),
            3,
        )

    def test_history_failure_rolls_back_manual_selection(self):
        self.tied_group()
        preview = self.preview()
        with patch(
            "competitions.qualification._record_change",
            side_effect=RuntimeError("history unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                self.confirm(preview)
        self.assertFalse(TieResolution.objects.exists())
        self.saved.stage.refresh_from_db()
        self.assertEqual(self.saved.stage.status, Stage.Status.AWAITING)

    def test_unfinished_parent_wrong_subset_and_extra_budget(self):
        self.saved = self.published_group(tiebreaks=())
        self.group = self.saved.groups.get()
        ids = list(self.group.entries.values_list("pk", flat=True))
        self.competition.refresh_from_db()
        with self.assertRaises(ValidationError):
            preview_group_tie(
                actor=self.actor,
                group_id=self.group.pk,
                expected_revision=self.competition.revision,
                tied_entry_ids=ids,
                method="MANUAL",
                ordered_entry_ids=ids,
            )
        for match in Match.objects.filter(round__draw=self.saved):
            self.result(match)
        with self.assertRaises(ValidationError):
            self.preview(tied_entry_ids=ids[:2], ordered_entry_ids=ids[:2])
        with patch("competitions.qualification.MAX_MATCHES", 2):
            with self.assertRaises(ValidationError):
                self.preview(method="EXTRA_MATCHES")
            self.preview()
        resolution = self.confirm(self.preview(method="EXTRA_MATCHES"))
        with self.assertRaises(ValidationError):
            self.preview(parent=resolution.pk)

    def test_ranking_irrelevant_score_correction_revalidates_manual_decision(self):
        ids = self.tied_group()
        resolution = self.confirm(self.preview())
        target = Match.objects.filter(round__draw=self.saved).first()
        # Fixed 2 is a draw; an equivalent played result leaves every ranking input unchanged.
        self.competition.refresh_from_db()
        preview = preview_correction(
            actor=self.actor,
            match_id=target.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=1,
            side_two_score=1,
        )
        self.assertEqual(preview["group_impact"]["invalidated_resolution_ids"], [])
        self.assertEqual(
            preview["group_impact"]["revalidated_resolution_ids"], [resolution.pk]
        )
        apply_correction(
            actor=self.actor, token=preview["token"], internal_reason="Rechecked"
        )
        self.assertEqual(group_standings(self.group)["qualifiers"], [ids[-1]])

    def test_correction_history_failure_rolls_back_decision_and_scores(self):
        self.tied_group()
        resolution = self.confirm(self.preview())
        target = Match.objects.filter(round__draw=self.saved).first()
        self.competition.refresh_from_db()
        preview = preview_correction(
            actor=self.actor,
            match_id=target.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        with patch(
            "competitions.commands._record_change",
            side_effect=RuntimeError("history unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                apply_correction(
                    actor=self.actor, token=preview["token"], internal_reason="Typo"
                )
        target.refresh_from_db()
        resolution.refresh_from_db()
        self.assertEqual((target.side_one_score, target.side_two_score), (1, 1))
        self.assertEqual(resolution.state, TieResolution.State.CONFIRMED)
