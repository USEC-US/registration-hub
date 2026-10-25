from concurrent.futures import ThreadPoolExecutor
import json
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from competitions import commands, swiss_commands
from competitions.models import ChangeSet, Match, Round, Stage, StageDraw
from competitions.serializers import PublicStageSerializer
from competitions.tests import test_swiss_commands as fixtures


class SwissApiTests(TestCase):
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
    _rematch_dead_end = fixtures.SwissCommandTests._rematch_dead_end

    def _stage_data(self):
        response = self.client.get(f"/api/competition-stages/{self.stage.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _overview(self):
        return self.client.get(f"/api/tournament-games/{self.division.pk}/competition/")

    def _changes(self, **query):
        response = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/changes/", query
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _assert_private(self, round_):
        self.assertEqual(
            self.client.get(f"/api/competition-rounds/{round_.pk}/").status_code, 404
        )
        for match in round_.matches.all():
            self.assertEqual(
                self.client.get(f"/api/competition-matches/{match.pk}/").status_code,
                404,
            )
        for stage in (self._stage_data(), self._overview().json()["stages"][0]):
            self.assertNotIn(round_.pk, [r["id"] for r in stage["rounds"]])
            self.assertTrue(
                set(round_.matches.values_list("pk", flat=True)).isdisjoint(
                    m["id"] for r in stage["rounds"] for m in r["matches"]
                )
            )

    def test_private_swiss_round_is_inaccessible_inside_published_draw(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        before = self._stage_data()
        draft = self._generate()
        bye = draft.matches.get(slots__is_empty=True)
        Match.objects.filter(pk=bye.pk).update(
            status="FINAL", outcome="BYE", winner_id=bye.slots.get(position=1).entry_id
        )
        self._assert_private(draft)
        after = self._stage_data()
        self.assertEqual(after["rounds"], before["rounds"])
        self.assertEqual(after["swiss_standings"], before["swiss_standings"])
        self.assertEqual(after["qualification"], before["qualification"])
        self.assertEqual(sum(row["bye_count"] for row in after["swiss_standings"]), 1)
        self.assertGreater(
            after["competition_revision"], before["competition_revision"]
        )
        self.assertEqual(
            self._changes()["competition_revision"], after["competition_revision"]
        )
        self.assertNotIn(
            "swiss_round_saved", [c["kind"] for c in self._changes()["results"]]
        )

    def test_superseded_private_preview_stays_private(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        old = self._generate()
        replacement = self._generate(regenerate=True)
        self._assert_private(old)
        self._assert_private(replacement)
        self.assertEqual(len(self._stage_data()["rounds"]), 1)

    def test_published_round_is_current_and_superseded_public_match_is_historical(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        second = self._generate()
        self._publish(second)
        self._finish(second)
        draft = self._generate()
        old_match = second.matches.exclude(outcome="BYE").first()
        before = self.client.get(f"/api/competition-matches/{old_match.pk}/").json()
        self.assertFalse(before["historical"])
        self.assertEqual(
            self.client.get(f"/api/competition-rounds/{second.pk}/").status_code, 200
        )
        preview = commands.preview_correction(
            actor=self.actor,
            match_id=draw.rounds.get(number=1)
            .matches.exclude(outcome="BYE")
            .first()
            .pk,
            expected_revision=self._revision(),
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        commands.apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="PRIVATE correction",
        )
        self._assert_private(draft)
        self.assertEqual(
            self.client.get(f"/api/competition-rounds/{second.pk}/").status_code, 404
        )
        detail = self.client.get(f"/api/competition-matches/{old_match.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["historical"])
        self.assertEqual(detail.json()["side_one_score"], before["side_one_score"])
        self.assertEqual(
            [r["id"] for r in self._stage_data()["rounds"]],
            [draw.rounds.get(number=1).pk],
        )
        change = next(
            c
            for c in self._changes(stage=self.stage.pk)["results"]
            if c["kind"] == "result_corrected"
        )
        self.assertEqual(
            change["swiss_impact"],
            {
                "retired_round_ids": [second.pk],
                "retired_match_ids": list(second.matches.values_list("pk", flat=True)),
            },
        )
        self.assertNotIn("PRIVATE correction", json.dumps(change))

    def test_historical_access_requires_both_round_and_draw_publication(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        public = draw.rounds.get()
        draft = self._generate()
        StageDraw.objects.filter(pk=draw.pk).update(state="SUPERSEDED")
        self._assert_private(draft)
        public_match = public.matches.first()
        response = self.client.get(f"/api/competition-matches/{public_match.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["historical"])
        self.assertEqual(self._stage_data()["draw_state"], "AWAITING_REPLACEMENT")
        self.assertEqual(self._stage_data()["swiss_standings"], [])
        self.assertIsNone(self._stage_data()["swiss_rules"]["round_limit"])
        self.assertEqual(self._stage_data()["qualification"]["state"], "PROVISIONAL")
        self.assertEqual(self._stage_data()["qualification"]["qualifiers"], [])
        StageDraw.objects.filter(pk=draw.pk).update(published_at=None)
        self.assertEqual(
            self.client.get(f"/api/competition-matches/{public_match.pk}/").status_code,
            404,
        )
        StageDraw.objects.filter(pk=draw.pk).update(published_at=timezone.now())
        Round.objects.filter(pk=public.pk).update(state="SUPERSEDED", published_at=None)
        self.assertEqual(
            self.client.get(f"/api/competition-matches/{public_match.pk}/").status_code,
            404,
        )

    def test_swiss_rules_and_standings_are_explicit_public_contracts(self):
        draw = self._draw(4)
        first = draw.rounds.get().matches.first()
        commands.finalize_match(
            actor=self.actor,
            match_id=first.pk,
            expected_revision=self._revision(),
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        data = self._stage_data()
        self.assertEqual(
            data["swiss_rules"],
            {
                "round_policy": "AUTOMATIC",
                "round_limit": 2,
                "win_target": None,
                "loss_limit": None,
                "win_points": "3.00",
                "draw_points": "1.00",
                "loss_points": "0.00",
                "tiebreaks": ["OPPONENT_POINTS", "GAME_DIFFERENCE", "GAMES_WON"],
            },
        )
        winner = next(
            row
            for row in data["swiss_standings"]
            if row["entry"]["id"] == first.slots.get(position=1).entry_id
        )
        self.assertEqual(
            set(winner),
            {
                "entry",
                "rank",
                "played",
                "wins",
                "draws",
                "losses",
                "points",
                "games_won",
                "game_difference",
                "opponent_points",
                "bye_count",
                "status",
            },
        )
        self.assertEqual(
            set(winner["entry"]), {"id", "seed", "display_name", "display_tag"}
        )
        self.assertEqual(
            {k: v for k, v in winner.items() if k != "entry"},
            {
                "rank": 1,
                "played": 1,
                "wins": 1,
                "draws": 0,
                "losses": 0,
                "points": "3.00",
                "games_won": 2,
                "game_difference": 2,
                "opponent_points": "0.00",
                "bye_count": 0,
                "status": "ACTIVE",
            },
        )
        for private_key in (
            "source_fingerprint",
            "version",
            "actor",
            "internal_reason",
            "registration_id",
            "rematches_authorized",
        ):
            self.assertNotIn(private_key, json.dumps(data))
        self.assertIsNone(data["champion"])

    def test_custom_policy_and_threshold_actual_qualifiers(self):
        draw = self._draw(
            5,
            format="SWISS_THRESHOLD",
            win_target=1,
            loss_limit=1,
            advancement_count=None,
        )
        self._finish(draw.rounds.get())
        data = self._stage_data()
        self.assertEqual(data["swiss_rules"]["round_policy"], "THRESHOLD")
        self.assertEqual(data["swiss_rules"]["round_limit"], 1)
        self.assertEqual(
            (data["swiss_rules"]["win_target"], data["swiss_rules"]["loss_limit"]),
            (1, 1),
        )
        self.assertIsNone(data["qualification"]["advance_count"])
        self.assertEqual(data["qualification"]["state"], "RESOLVED")
        self.assertEqual(len(data["qualification"]["qualifiers"]), 3)
        self.assertEqual(
            [r["status"] for r in data["swiss_standings"]].count("QUALIFIED"), 3
        )
        self.assertIsNone(data["champion"])
        self.assertEqual(data["status"], "COMPLETE")

    def test_custom_round_policy(self):
        self._draw(4, round_count=1)
        self.assertEqual(self._stage_data()["swiss_rules"]["round_policy"], "CUSTOM")
        self.assertEqual(self._stage_data()["swiss_rules"]["round_limit"], 1)

    def test_swiss_never_serializes_a_champion(self):
        self._draw(4)
        self.stage.champion = self.entrants[0]
        self.stage.save(update_fields=("champion",))
        self.assertIsNone(self._stage_data()["champion"])

    def test_publication_changes_allowlist_matches_and_pairing_exceptions(self):
        self._rematch_dead_end()
        saved = self._generate(
            allow_rematches=True, internal_reason="PRIVATE rematch authorization"
        )
        self.assertNotIn(
            "swiss_round_saved", [c["kind"] for c in self._changes()["results"]]
        )
        self._publish(saved)
        change = self.competition.changes.get(revision=self._revision())
        change.public_data.update(
            actor="PRIVATE actor",
            internal_reason="PRIVATE reason",
            source_fingerprint="PRIVATE fingerprint",
            version=99,
        )
        change.save(update_fields=("public_data",))
        event = self._changes(stage=self.stage.pk)["results"][0]
        self.assertEqual(
            event,
            {
                "kind": "swiss_round_published",
                "revision": change.revision,
                "created_at": change.created_at.isoformat(),
                "stage_id": self.stage.pk,
                "round_id": saved.pk,
                "round_number": 3,
                "match_ids": list(saved.matches.values_list("pk", flat=True)),
                "rematch_count": 1,
                "repeated_bye": False,
                "automatic_results": [],
            },
        )
        self.assertEqual(len(self._stage_data()["rounds"]), 3)
        self.assertIsNone(self._stage_data()["champion"])

    def test_public_pending_retirement_and_nested_impact_allowlist(self):
        draw = self._draw(4)
        self._finish(draw.rounds.get())
        pending = self._generate()
        self._publish(pending)
        preview = commands.preview_correction(
            actor=self.actor,
            match_id=draw.rounds.get(number=1).matches.first().pk,
            expected_revision=self._revision(),
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        commands.apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="PRIVATE correction",
        )
        change = self.competition.changes.get(kind="result_corrected")
        change.public_data["swiss_impact"].update(
            played_match_ids=[999999],
            current_match_ids=[999999],
            actor="PRIVATE actor",
            source_fingerprint="PRIVATE fingerprint",
        )
        change.save(update_fields=("public_data",))
        event = self._changes(stage=self.stage.pk)["results"][0]
        self.assertEqual(
            event["swiss_impact"],
            {
                "retired_round_ids": [pending.pk],
                "retired_match_ids": list(pending.matches.values_list("pk", flat=True)),
            },
        )
        self.assertEqual(event["reset_matches"], [])
        self.assertNotIn("PRIVATE", json.dumps(event))
        detail = self.client.get(
            f"/api/competition-matches/{pending.matches.first().pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["historical"])

    def test_reads_reuse_saved_preview_and_queries_do_not_grow_per_match(self):
        draw = self._draw(16)
        self._finish(draw.rounds.get())
        with CaptureQueriesContext(connection) as queries:
            self._overview()
        initial_count = len(queries)
        saved = self._generate()
        self._publish(saved)
        revision = self._revision()
        with patch.object(
            swiss_commands,
            "pair_swiss_round",
            side_effect=AssertionError("GET solved pairings"),
        ):
            with CaptureQueriesContext(connection) as queries:
                response = self._overview()
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(len(queries), initial_count + 2)
            self.assertLessEqual(len(queries), 30)
            self._stage_data()
            self._changes()
        self.assertEqual(self._revision(), revision)
        self.assertEqual(draw.rounds.count(), 2)

    def test_unpublished_parent_hides_swiss_and_history(self):
        draw = self._draw()
        round_ = draw.rounds.get()
        self.division.tournament.is_published = False
        self.division.tournament.save(update_fields=("is_published",))
        for url in (
            f"/api/tournament-games/{self.division.pk}/competition/",
            f"/api/tournament-games/{self.division.pk}/competition/changes/",
            f"/api/competition-stages/{self.stage.pk}/",
            f"/api/competition-rounds/{round_.pk}/",
            f"/api/competition-matches/{round_.matches.first().pk}/",
        ):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_serializer_round_boundary_is_safe_without_prefetch(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        self._generate()
        data = PublicStageSerializer(Stage.objects.get(pk=self.stage.pk)).data
        self.assertEqual(len(data["rounds"]), 1)
        self.assertEqual(sum(row["bye_count"] for row in data["swiss_standings"]), 1)

    def test_publication_bye_snapshot_is_allowlisted_and_revision_paginated(self):
        draw = self._draw()
        initial = self._changes()["results"][0]
        self.assertEqual(initial["round_number"], 1)
        self.assertEqual(
            initial["match_ids"],
            list(draw.rounds.get().matches.values_list("pk", flat=True)),
        )
        self.assertEqual(initial["rematch_count"], 0)
        self.assertFalse(initial["repeated_bye"])
        self.assertEqual(len(initial["automatic_results"]), 1)
        self._finish(draw.rounds.get())
        saved = self._generate()
        gap_revision = self._revision()
        self._publish(saved)
        change = self.competition.changes.get(revision=self._revision())
        change.public_data["automatic_results"][0].update(
            actor="PRIVATE actor",
            registration_id=999999,
            source_fingerprint="PRIVATE fingerprint",
        )
        change.save(update_fields=("public_data",))
        page = self._changes(page_size=1)
        self.assertEqual(page["results"][0]["round_number"], 2)
        self.assertEqual(len(page["results"][0]["automatic_results"]), 1)
        self.assertNotIn("PRIVATE", json.dumps(page))
        revisions = [page["results"][0]["revision"]]
        while page["next"]:
            page = self.client.get(page["next"]).json()
            revisions.extend(row["revision"] for row in page["results"])
            self.assertEqual(page["competition_revision"], self._revision())
        self.assertEqual(revisions, sorted(set(revisions), reverse=True))
        self.assertNotIn(gap_revision, revisions)
        self.assertIn(initial["revision"], revisions)

    def test_stage_filtered_changes_does_not_resolve_private_match_ids(self):
        draw = self._draw()
        self._finish(draw.rounds.get())
        private = self._generate()
        private_change = self.competition.changes.get(revision=self._revision())
        # A legacy match-only event must not resolve its stage through a private row.
        private_change.public_data = {
            "kind": "legacy_match_event",
            "match_id": private.matches.first().pk,
        }
        private_change.save(update_fields=("public_data",))
        filtered = self._changes(stage=self.stage.pk)["results"]
        self.assertNotIn(
            private_change.revision, [event["revision"] for event in filtered]
        )
        public_match = draw.rounds.get(number=1).matches.first()
        latest = ChangeSet.objects.filter(
            competition=self.competition, public_data__match_id=public_match.pk
        ).latest("revision")
        self.assertIn(latest.revision, [event["revision"] for event in filtered])

    def test_repeated_threshold_bye_is_public_without_authorization_details(self):
        draw = self._draw(
            3,
            format="SWISS_THRESHOLD",
            win_target=3,
            loss_limit=1,
            advancement_count=None,
        )
        match = draw.rounds.get().matches.exclude(outcome="BYE").get()
        commands.finalize_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=self._revision(),
            outcome="DOUBLE_FORFEIT",
        )
        saved = self._generate()
        self._publish(saved)
        event = self._changes()["results"][0]
        self.assertTrue(event["repeated_bye"])
        self.assertEqual(event["rematch_count"], 0)
        self.assertEqual(len(event["match_ids"]), 1)
        self.assertEqual(len(event["automatic_results"]), 1)
        self.assertEqual(
            sum(row["bye_count"] for row in self._stage_data()["swiss_standings"]), 2
        )
        self.assertNotIn("internal_reason", event)
        self.assertNotIn("actor", event)

    def test_fixed_cutoff_uses_shared_public_qualification_contract(self):
        draw = self._draw(4, round_count=1, tiebreaks=[])
        self._finish(draw.rounds.get())
        data = self._stage_data()
        self.assertEqual(data["qualification"]["state"], "RESOLVED")
        self.assertEqual(data["qualification"]["advance_count"], 2)
        self.assertEqual(len(data["qualification"]["qualifiers"]), 2)
        self.assertEqual([row["rank"] for row in data["swiss_standings"]], [1, 1, 3, 3])
        self.assertIsNone(data["champion"])

    def test_fixed_cutoff_ties_are_public_without_private_fingerprint(self):
        draw = self._draw(4, round_count=1, advancement_count=3, tiebreaks=[])
        self._finish(draw.rounds.get())
        qualification = self._stage_data()["qualification"]
        self.assertEqual(qualification["state"], "AWAITING_RESOLUTION")
        self.assertEqual(qualification["advance_count"], 3)
        self.assertEqual(len(qualification["qualifiers"]), 2)
        self.assertEqual(len(qualification["cutoff_ties"]), 1)
        tie = qualification["cutoff_ties"][0]
        self.assertEqual(tie["places"], 1)
        self.assertEqual(len(tie["tied_entries"]), 2)
        self.assertEqual(tie["round_ids"], [])
        self.assertIsNone(tie["resolution_id"])
        self.assertNotIn("source_fingerprint", json.dumps(qualification))


class SwissSnapshotApiTests(TransactionTestCase):
    setUp = SwissApiTests.setUp
    _registration = SwissApiTests._registration
    _competition = SwissApiTests._competition
    _swiss = SwissApiTests._swiss
    _elimination = SwissApiTests._elimination
    _revision = SwissApiTests._revision
    _draw = SwissApiTests._draw
    _finish = SwissApiTests._finish
    _generate = SwissApiTests._generate

    def test_private_preview_commit_between_reads_preserves_snapshot_revision(self):
        from competitions.serializers import PublicCompetitionSerializer
        from competitions.views import (
            _published_competition_queryset,
            consistent_public_read,
        )

        draw = self._draw(4)
        self._finish(draw.rounds.get())
        revision = self._revision()

        def save_preview():
            close_old_connections()
            try:
                return self._generate().pk
            finally:
                close_old_connections()

        with consistent_public_read():
            before = PublicCompetitionSerializer(
                _published_competition_queryset().get(pk=self.competition.pk)
            ).data
            with ThreadPoolExecutor(max_workers=1) as executor:
                saved_id = executor.submit(save_preview).result(timeout=30)
            after = PublicCompetitionSerializer(
                _published_competition_queryset().get(pk=self.competition.pk)
            ).data
            self.assertEqual(after, before)
            self.assertEqual(after["competition_revision"], revision)
            self.assertFalse(Round.objects.filter(pk=saved_id).exists())
        response = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["competition_revision"], revision + 1)
        self.assertEqual(
            response.json()["stages"][0]["rounds"], before["stages"][0]["rounds"]
        )
        self.assertEqual(
            response.json()["stages"][0]["swiss_standings"],
            before["stages"][0]["swiss_standings"],
        )
