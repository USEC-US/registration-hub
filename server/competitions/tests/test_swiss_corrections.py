from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from competitions import commands, swiss_commands
from competitions.models import Match
from competitions.swiss_corrections import project_swiss_correction
from competitions.qualification import (
    confirm_qualification_tie,
    preview_qualification_tie,
    stage_qualification,
    projected_fixture_matches,
)
from competitions.tests import test_swiss_handoffs as fixtures


class SwissCorrectionTests(TestCase):
    setUp = fixtures.SwissHandoffTests.setUp
    _registration = fixtures.SwissHandoffTests._registration
    _competition = fixtures.SwissHandoffTests._competition
    _swiss = fixtures.SwissHandoffTests._swiss
    _elimination = fixtures.SwissHandoffTests._elimination
    _revision = fixtures.SwissHandoffTests._revision
    _finish = fixtures.SwissHandoffTests._finish
    _generate = fixtures.SwissHandoffTests._generate
    _publish = fixtures.SwissHandoffTests._publish
    _save_source = fixtures.SwissHandoffTests._save_source
    _publish_draw = fixtures.SwissHandoffTests._publish_draw
    _next = fixtures.SwissHandoffTests._next
    _finish_draw = fixtures.SwissHandoffTests._finish_draw

    def _source(self, *, rounds=3, quota=8, **rules):
        self._competition(8)
        self.stage = self._swiss(round_count=rounds, advancement_count=quota, **rules)
        self.destination = self._elimination(2, quota=2)
        self._elimination(3)
        source = self._save_source()
        self._finish(source.rounds.get())
        return source

    def _later_round(self, *, publish=True, finish=True):
        round_ = self._generate()
        if publish:
            self._publish(round_)
            if finish:
                self._finish(round_)
        return round_

    def _preview(self, match, **result):
        return commands.preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self._revision(),
            outcome=result.pop("outcome", "PLAYED"),
            **(dict(side_one_score=0, side_two_score=2) | result),
        )

    def _apply(self, preview):
        return commands.apply_correction(
            actor=self.actor, token=preview["token"], internal_reason="Correct result"
        )

    def _saved(self, source):
        return list(
            Match.objects.filter(round__draw=source)
            .order_by("pk")
            .values_list(
                "pk", "code", "status", "side_one_score", "side_two_score", "winner_id"
            )
        )

    def test_earlier_correction_retires_all_later_rounds_and_downstream_play(self):
        source = self._source()
        later = [self._later_round(), self._later_round()]
        draws = []
        for stage in (self.destination, self.competition.stages.get(sequence=3)):
            draw = self._next(stage)
            self._publish_draw(draw)
            self._finish_draw(draw)
            draws.append(draw)
        snapshots = [self._saved(draw) for draw in [source, *draws]]
        match = source.rounds.get(number=1).matches.first()
        preview = self._preview(match)
        impact = preview["swiss_impact"]
        self.assertEqual(impact["retired_round_ids"], [r.pk for r in later])
        self.assertEqual(
            set(impact["retired_match_ids"]),
            {m.pk for r in later for m in r.matches.all()},
        )
        self.assertEqual(impact["played_match_ids"], impact["retired_match_ids"])
        self.assertEqual(preview["affected_matches"], [])
        self.assertEqual(
            preview["handoff_impact"]["superseded_draw_ids"], [d.pk for d in draws]
        )
        self.assertEqual(self._saved(source), snapshots[0])
        self.assertEqual(
            set(impact["current_match_ids"]),
            set(source.rounds.get(number=1).matches.values_list("pk", flat=True)),
        )
        with (
            patch(
                "competitions.commands._record_change",
                side_effect=RuntimeError("history failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._apply(preview)
        self.assertEqual(self._saved(source), snapshots[0])
        for draw, old in zip(draws, snapshots[1:], strict=True):
            draw.refresh_from_db()
            self.assertEqual(draw.state, "PUBLISHED")
            self.assertEqual(self._saved(draw), old)
        self.assertEqual(source.rounds.filter(state="PUBLISHED").count(), 3)
        self._apply(preview)
        for round_ in later:
            round_.refresh_from_db()
            self.assertEqual(round_.state, "SUPERSEDED")
        for draw, old in zip(draws, snapshots[1:], strict=True):
            draw.refresh_from_db()
            self.assertEqual(draw.state, "SUPERSEDED")
            self.assertEqual(self._saved(draw), old)
        self.assertEqual(self._saved(source)[1:], snapshots[0][1:])
        self.assertEqual(sum(r.wins for r in swiss_commands.swiss_standings(source)), 4)
        self.assertEqual(
            stage_qualification(source)["qualification_state"], "PROVISIONAL"
        )
        change = self.competition.changes.get(kind="result_corrected")
        self.assertEqual(
            change.private_data["before"]["winner"], match.winner.entrant.display_name
        )
        self.assertEqual(change.private_data["swiss_impact"], impact)
        replacement = self._generate()
        self.assertEqual(replacement.number, later[0].number)
        self.assertGreater(replacement.version, later[0].version)
        self._publish(replacement)
        self._finish(replacement)
        self._publish(self._generate())
        self.assertFalse(
            set(impact["retired_match_ids"])
            & {m.pk for m in commands._ordered_matches(source)}
        )

    def test_later_private_preview_retires_and_stays_out_of_public_changes(self):
        source = self._source()
        published = self._later_round()
        draft = self._later_round(publish=False)
        old = self._saved(source)
        preview = self._preview(source.rounds.get(number=1).matches.first())
        self.assertEqual(
            preview["swiss_impact"]["retired_round_ids"], [published.pk, draft.pk]
        )
        draft_ids = set(draft.matches.values_list("pk", flat=True))
        self._apply(preview)
        self.assertEqual(self._saved(source)[4:], old[4:])
        change = self.competition.changes.get(kind="result_corrected")
        self.assertEqual(
            change.public_data["swiss_impact"],
            {
                "retired_round_ids": [published.pk],
                "retired_match_ids": list(
                    published.matches.values_list("pk", flat=True)
                ),
            },
        )
        self.assertFalse(
            draft_ids & {m["match_id"] for m in change.public_data["reset_matches"]}
        )
        self.assertTrue(
            draft_ids <= set(change.private_data["swiss_impact"]["retired_match_ids"])
        )

    def test_score_only_correction_invalidates_configured_game_tiebreak(self):
        source = self._source()
        later = self._later_round(publish=False)
        preview = self._preview(
            source.rounds.get(number=1).matches.first(),
            side_one_score=2,
            side_two_score=1,
        )
        self.assertEqual(preview["swiss_impact"]["retired_round_ids"], [later.pk])
        self._apply(preview)
        later.refresh_from_db()
        self.assertEqual(later.state, "SUPERSEDED")

    def test_identical_inputs_and_ignored_game_scores_preserve_later_round(self):
        source = self._source(tiebreaks=["OPPONENT_POINTS"])
        later = self._later_round(publish=False)
        match = source.rounds.get(number=1).matches.first()
        for scores in ((2, 0), (2, 1)):
            preview = self._preview(
                match, side_one_score=scores[0], side_two_score=scores[1]
            )
            self.assertEqual(preview["swiss_impact"]["retired_round_ids"], [])
            self._apply(preview)
        later.refresh_from_db()
        self.assertEqual(later.state, "DRAFT")
        self._publish(later)

    def test_schedule_only_change_preserves_saved_preview_and_source(self):
        self._source()
        later = self._later_round(finish=False)
        fingerprint = later.source_fingerprint
        commands.schedule_match(
            actor=self.actor,
            match_id=later.matches.first().pk,
            expected_revision=self._revision(),
            scheduled_at=None,
        )
        swiss_commands.validate_swiss_round(later, verify_pairing=False)
        later.refresh_from_db()
        self.assertEqual(later.source_fingerprint, fingerprint)
        self.assertEqual(later.state, "PUBLISHED")

    def test_replay_and_intervening_result_leave_history_unchanged(self):
        source = self._source()
        later = self._later_round(finish=False)
        match = source.rounds.get(number=1).matches.first()
        stale = self._preview(match)
        self._finish(later)
        saved = self._saved(source)
        with self.assertRaises(ValidationError):
            self._apply(stale)
        self.assertEqual(self._saved(source), saved)
        preview = self._preview(match)
        self._apply(preview)
        saved = self._saved(source)
        with self.assertRaises(ValidationError):
            self._apply(preview)
        self.assertEqual(self._saved(source), saved)
        with self.assertRaises(ValidationError):
            self._preview(later.matches.first())

    def test_retirement_rolls_back_if_history_recording_fails(self):
        source = self._source()
        later = self._later_round()
        draft = self._later_round(publish=False)
        saved = self._saved(source)
        preview = self._preview(source.rounds.get(number=1).matches.first())
        with (
            patch(
                "competitions.commands._record_change",
                side_effect=RuntimeError("history failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._apply(preview)
        self.assertEqual(self._saved(source), saved)
        later.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual((later.state, draft.state), ("PUBLISHED", "DRAFT"))

    def test_final_round_unchanged_membership_preserves_successor_and_refreshes_fingerprint(
        self,
    ):
        source = self._source(rounds=2)
        final = self._later_round()
        successor = self._next(self.destination)
        self._publish_draw(successor)
        self._finish_draw(successor)
        old, fingerprint = self._saved(successor), successor.source_fingerprint
        preview = self._preview(
            final.matches.first(), side_one_score=2, side_two_score=1
        )
        self.assertEqual(preview["swiss_impact"]["retired_round_ids"], [])
        self.assertEqual(preview["handoff_impact"]["retained_draw_ids"], [successor.pk])
        self._apply(preview)
        successor.refresh_from_db()
        self.assertEqual(successor.state, "PUBLISHED")
        self.assertEqual(self._saved(successor), old)
        self.assertNotEqual(successor.source_fingerprint, fingerprint)
        self.assertEqual(
            successor.source_fingerprint, stage_qualification(source)["fingerprint"]
        )

    def test_cutoff_contests_retire_with_changed_source_and_keep_scores(self):
        source = self._source(rounds=1, quota=2, tiebreaks=[])
        tie = stage_qualification(source)["cutoffs"][0]
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=source.pk,
            expected_revision=self._revision(),
            tied_entry_ids=tie["entry_ids"],
            method="EXTRA_MATCHES",
        )
        resolution = confirm_qualification_tie(actor=self.actor, token=preview["token"])
        for match in Match.objects.filter(round__tie_resolution=resolution):
            slots = list(match.slots.order_by("position"))
            first_wins = slots[0].resolved_entry_id < slots[1].resolved_entry_id
            commands.finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self._revision(),
                outcome="PLAYED",
                side_one_score=int(first_wins),
                side_two_score=int(not first_wins),
            )
        successor = self._next(self.destination)
        self._publish_draw(successor)
        self._finish_draw(successor)
        saved = self._saved(source)
        successor_saved = self._saved(successor)
        correction = self._preview(source.rounds.get(section="NORMAL").matches.first())
        self.assertTrue(correction["swiss_impact"]["retired_round_ids"])
        self._apply(correction)
        resolution.refresh_from_db()
        self.assertEqual(resolution.state, "SUPERSEDED")
        successor.refresh_from_db()
        self.assertEqual(successor.state, "SUPERSEDED")
        self.assertEqual(self._saved(successor), successor_saved)
        self.assertEqual(self._saved(source)[4:], saved[4:])
        self.assertEqual(sum(r.wins for r in swiss_commands.swiss_standings(source)), 4)

    def test_admin_preview_and_missing_confirmation_leave_state_unchanged(self):
        source = self._source()
        later = self._later_round()
        saved = self._saved(source)
        match = source.rounds.get(number=1).matches.first()
        url = reverse("admin:competitions_match_correct_detail", args=[match.pk])
        self.client.force_login(self.actor)
        response = self.client.post(
            url,
            dict(
                expected_revision=self._revision(),
                outcome="PLAYED",
                side_one_score=0,
                side_two_score=2,
            ),
        )
        self.assertEqual(response.status_code, 200)
        impact = response.context["impact"]
        self.assertEqual(
            impact["swiss_impact"]["played_match_ids"],
            list(later.matches.values_list("pk", flat=True)),
        )
        self.assertEqual(self._saved(source), saved)
        response = self.client.post(url, {"internal_reason": "No signed confirmation"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._saved(source), saved)
        response = self.client.post(url, {"token": impact["token"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._saved(source), saved)
        later.refresh_from_db()
        self.assertEqual(later.state, "PUBLISHED")
        response = self.client.post(
            url, {"token": impact["token"], "internal_reason": "Confirmed resets"}
        )
        self.assertEqual(response.status_code, 302)
        later.refresh_from_db()
        self.assertEqual(later.state, "SUPERSEDED")

    def test_complete_projection_omits_retired_rows_and_ignores_foreign_fixtures(self):
        source = self._source(rounds=2)
        later = self._later_round()
        successor = self._next(self.destination)
        self._publish_draw(successor)
        self._finish_draw(successor)
        retained = list(
            Match.objects.filter(round__draw=source, round__number=1).select_related(
                "round"
            )
        )
        foreign = list(
            Match.objects.filter(round__draw=successor).select_related("round")
        )
        self.assertEqual(
            {m.pk for m in projected_fixture_matches(source, retained + foreign)},
            {m.pk for m in retained},
        )
        impact = project_swiss_correction(source, projected_matches=retained + foreign)
        self.assertEqual(set(impact["current_match_ids"]), {m.pk for m in retained})
        rows = swiss_commands.swiss_standings(
            source, projected_matches=retained + foreign
        )
        self.assertEqual(sum(r.played for r in rows), 8)
        self.assertEqual(sum(r.wins for r in rows), 4)
        self.assertEqual(
            stage_qualification(source, projected_matches=retained)[
                "qualification_state"
            ],
            "PROVISIONAL",
        )
        self.assertEqual(
            stage_qualification(source, projected_matches=[])["bands"],
            [[e.pk for e in source.entries.order_by("seed")]],
        )
        later.refresh_from_db()
        self.assertEqual(later.state, "PUBLISHED")

    def test_threshold_changed_qualified_count_retires_chain_and_replacement_uses_actual_field(
        self,
    ):
        self._competition(8)
        self.stage = self._swiss(
            format="SWISS_THRESHOLD", advancement_count=None, win_target=1, loss_limit=1
        )
        second = self._elimination(2, quota=2)
        third = self._elimination(3)
        source = self._save_source()
        self._finish(source.rounds.get())
        draws = []
        for stage in (second, third):
            draw = self._next(stage)
            self._publish_draw(draw)
            self._finish_draw(draw)
            draws.append(draw)
        saved = [self._saved(d) for d in draws]
        preview = self._preview(
            source.rounds.get().matches.first(),
            outcome="DOUBLE_FORFEIT",
            side_one_score=None,
            side_two_score=None,
        )
        self.assertEqual(
            preview["handoff_impact"]["superseded_draw_ids"], [d.pk for d in draws]
        )
        self._apply(preview)
        self.assertEqual(len(stage_qualification(source)["qualifier_entry_ids"]), 3)
        for draw, old in zip(draws, saved, strict=True):
            self.assertEqual(self._saved(draw), old)
        replacement = self._next(second)
        self.assertEqual(replacement.entries.count(), 3)
        self._publish_draw(replacement)

    def test_admin_stale_confirmation_and_replay_do_not_change_history(self):
        source = self._source()
        later = self._later_round(finish=False)
        match = source.rounds.get(number=1).matches.first()
        url = reverse("admin:competitions_match_correct_detail", args=[match.pk])
        self.client.force_login(self.actor)
        preview = self._preview(match)
        self._finish(later)
        saved = self._saved(source)
        response = self.client.post(
            url, {"token": preview["token"], "internal_reason": "Confirmed resets"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._saved(source), saved)
        preview = self._preview(match)
        response = self.client.post(
            url, {"token": preview["token"], "internal_reason": "Confirmed resets"}
        )
        self.assertEqual(response.status_code, 302)
        saved = self._saved(source)
        response = self.client.post(
            url, {"token": preview["token"], "internal_reason": "Replay"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._saved(source), saved)

    def test_public_retirement_includes_published_pending_matches(self):
        source = self._source()
        pending = self._later_round(finish=False)
        preview = self._preview(source.rounds.get(number=1).matches.first())
        self.assertEqual(preview["swiss_impact"]["played_match_ids"], [])
        self._apply(preview)
        change = self.competition.changes.get(kind="result_corrected")
        self.assertEqual(
            change.public_data["swiss_impact"],
            {
                "retired_round_ids": [pending.pk],
                "retired_match_ids": list(pending.matches.values_list("pk", flat=True)),
            },
        )
        self.assertEqual(change.public_data["reset_matches"], [])
