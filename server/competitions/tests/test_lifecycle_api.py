from competitions.tests import test_competition_lifecycle as lifecycle_fixtures
from competitions import lifecycle_commands as lifecycle
from competitions.tests import test_swiss_commands as swiss_fixtures
from rest_framework.test import APITestCase
from competitions.tests import test_api as fixtures
from competitions.models import ChangeSet, Competition, CompetitionEntrant, StageDraw


class PublicLifecycleApiTests(APITestCase):
    setUp = fixtures.PublicCompetitionApiTests.setUp
    _registration = fixtures.PublicCompetitionApiTests._registration
    _publish = fixtures.PublicCompetitionApiTests._publish

    def overview(self):
        return self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        ).data

    def test_availability_ending_and_retired_history_are_read_only(self):
        from django.utils import timezone

        from competitions.commands import save_elimination_draw

        self.competition.refresh_from_db()
        self.draw = save_elimination_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            entrant_order=list(
                self.competition.entrants.order_by("pk").values_list("pk", flat=True)
            ),
        )
        self._publish()
        entry = self.draw.entries.select_related("entrant").first()
        self.assertNotEqual(entry.pk, entry.entrant_id)
        entry.entrant.status = "WITHDRAWN"
        entry.entrant.save(update_fields=["status"])
        self.assertEqual(
            self.overview()["stages"][0]["entries"][0]["status"], "WITHDRAWN"
        )
        Competition.objects.filter(pk=self.competition.pk).update(
            ended_at=timezone.now(),
            ended_stage=self.stage,
            ended_champion=entry.entrant,
        )
        before = list(Competition.objects.values())
        data = self.overview()
        self.assertEqual(data["ending"]["champion"]["id"], entry.entrant_id)
        self.assertEqual(data["stages"][0]["lifecycle_state"], "CLOSED")
        self.assertEqual(before, list(Competition.objects.values()))
        Competition.objects.filter(pk=self.competition.pk).update(ended_champion=None)
        self.assertIsNone(self.overview()["ending"]["champion"])
        Competition.objects.filter(pk=self.competition.pk).update(
            ended_at=None, ended_stage=None
        )
        StageDraw.objects.filter(pk=self.draw.pk).update(state="SUPERSEDED")
        self.stage.status = "AWAITING"
        self.stage.save(update_fields=["status"])
        data = self.overview()
        self.assertIsNone(data["ending"])
        self.assertEqual(data["stages"][0]["lifecycle_state"], "RETIRED")
        self.assertEqual(data["stages"][0]["draw_state"], "AWAITING_REPLACEMENT")
        match = self.draw.rounds.first().matches.first()
        self.assertTrue(data["stages"][0]["rounds"])
        historical = self.client.get(f"/api/competition-matches/{match.pk}/")
        self.assertEqual(historical.status_code, 200)
        self.assertTrue(historical.data["historical"])

    def test_nested_lifecycle_history_is_allowlisted(self):
        self._publish()
        secret = {
            "internal_reason": "SECRET",
            "actor": "SECRET",
            "earned_resolution_ids": [999],
            "removal_effect": {"registration_id": 999},
        }
        event = ChangeSet.objects.create(
            competition=self.competition,
            revision=self.competition.revision + 1,
            kind="entrant_withdrawn",
            public_data={
                "kind": "entrant_withdrawn",
                "entrant_id": 1,
                "display_name": "Public",
                "before": {"status": "ACTIVE", **secret},
                "after": {"status": "WITHDRAWN", **secret},
                "retired_draws": [self.draw.pk],
                "retired_rounds": [],
                "match_impacts": [
                    {
                        "match_id": self.draw.rounds.first().matches.first().pk,
                        "before": {"status": "LIVE", **secret},
                        "after": {"frozen": True, **secret},
                        **secret,
                    }
                ],
                **secret,
            },
        )
        from competitions.serializers import PublicChangeSerializer

        data = PublicChangeSerializer(event).data
        self.assertEqual(data["after"], {"status": "WITHDRAWN"})
        self.assertEqual(data["retired_draws"], [self.draw.pk])
        self.assertEqual(data["match_impacts"][0]["after"], {"frozen": True})
        self.assertNotIn("SECRET", str(data))
        self.assertNotIn("999", str(data))


class LifecycleCommandPublicTests(APITestCase):
    setUp = lifecycle_fixtures.CompetitionLifecycleTests.setUp
    _registration = lifecycle_fixtures.CompetitionLifecycleTests._registration
    _chain = lifecycle_fixtures.CompetitionLifecycleTests._chain
    _finish = lifecycle_fixtures.CompetitionLifecycleTests._finish
    remove = lifecycle_fixtures.CompetitionLifecycleTests.remove
    preview = lifecycle_fixtures.CompetitionLifecycleTests.preview
    end = lifecycle_fixtures.CompetitionLifecycleTests.end

    def _public(self):
        tournament = self.division.tournament
        tournament.is_published = True
        tournament.save(update_fields=["is_published"])
        self.url = f"/api/tournament-games/{self.division.pk}/competition/"

    def test_explicit_sole_survivor_outcome_and_reopening_history(self):
        self.source, _ = self._chain()
        self._public()
        self._finish(self.source)
        entries = list(self.source.entries.select_related("entrant").order_by("seed"))
        for entry in entries[:3]:
            self.remove(entry.entrant)
        original = list(self.source.rounds.first().matches.values())
        self.end(self.preview(True))
        data = self.client.get(self.url).data
        self.assertEqual(data["ending"]["champion"]["id"], entries[3].entrant_id)
        self.assertEqual(
            data["ending"]["champion"]["display_name"], entries[3].entrant.display_name
        )
        history = self.client.get(self.url + "changes/").data
        self.assertEqual(history["competition_revision"], data["competition_revision"])
        ending = history["results"][0]
        self.assertEqual(ending["after"]["champion"], data["ending"]["champion"])
        self.assertNotIn("champion_id", ending["after"])
        self.competition.refresh_from_db()
        reopen = lifecycle.preview_competition_reopen(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )
        lifecycle.apply_competition_reopen(
            actor=self.actor,
            token=reopen["token"],
            internal_reason="PRIVATE-REOPEN",
            confirm_resets=True,
        )
        self.assertIsNone(self.client.get(self.url).data["ending"])
        changes = self.client.get(self.url + "changes/").data["results"]
        self.assertEqual(changes[0]["kind"], "competition_reopened")
        self.assertEqual(changes[0]["before"]["champion"]["id"], entries[3].entrant_id)
        self.assertEqual(original, list(self.source.rounds.first().matches.values()))
        for forbidden in (
            "PRIVATE-REOPEN",
            "earned_resolution_ids",
            "internal_reason",
            "source_fingerprint",
            "removal_effect",
            "actor",
            "registration_id",
            "contact_phone",
        ):
            self.assertNotIn(forbidden, str(changes))

    def test_private_draft_impacts_and_retirements_are_absent(self):
        from competitions.handoff_commands import generate_next_stage_draw

        self.source, destination = self._chain()
        self._public()
        self._finish(self.source)
        draft = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        private_match_ids = set(draft.rounds.values_list("matches__pk", flat=True))
        self.remove(self.source.entries.first().entrant)
        change = self.client.get(self.url + "changes/").data["results"][0]
        self.assertNotIn(draft.pk, change.get("retired_draws", []))
        self.assertFalse(
            private_match_ids & {m["match_id"] for m in change["match_impacts"]}
        )
        self.assertFalse(
            private_match_ids & {m["match_id"] for m in change.get("reset_matches", [])}
        )

    def test_retired_played_suffix_keeps_scores_urls_and_replacement_navigation(self):
        from competitions import commands
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.models import Match, MatchSlot, Round, Stage

        self.source, destination = self._chain()
        self._public()
        self._finish(self.source)
        suffix = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        commands.publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            stage_id=destination.pk,
        )
        self._finish(suffix)
        match = suffix.rounds.first().matches.first()
        original = (match.side_one_score, match.side_two_score)
        entrant = self.source.entries.first().entrant
        entrant.registration.status = "REJECTED"
        entrant.registration.save(update_fields=["status"])
        self.end(self.preview(), confirm_resets=True)
        data = self.client.get(self.url).data
        self.assertIsNone(data["ending"]["champion"])
        stage = next(s for s in data["stages"] if s["id"] == destination.pk)
        self.assertEqual(stage["lifecycle_state"], "RETIRED")
        self.assertEqual(stage["draw_state"], "AWAITING_REPLACEMENT")
        self.assertTrue(stage["rounds"])
        before = [
            list(model.objects.values())
            for model in (
                Competition,
                CompetitionEntrant,
                Stage,
                StageDraw,
                Round,
                Match,
                MatchSlot,
                ChangeSet,
            )
        ]
        urls = [
            self.url,
            self.url + "changes/",
            self.url + f"changes/?stage={destination.pk}",
            f"/api/competition-stages/{destination.pk}/",
            f"/api/competition-rounds/{match.round_id}/",
            f"/api/competition-matches/{match.pk}/",
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertEqual(
                response.data["competition_revision"], data["competition_revision"]
            )
        result = self.client.get(urls[-1]).data
        self.assertEqual((result["side_one_score"], result["side_two_score"]), original)
        self.assertTrue(result["historical"])
        self.assertEqual(
            before,
            [
                list(model.objects.values())
                for model in (
                    Competition,
                    CompetitionEntrant,
                    Stage,
                    StageDraw,
                    Round,
                    Match,
                    MatchSlot,
                    ChangeSet,
                )
            ],
        )
        scoped = self.client.get(urls[2]).data["results"]
        self.assertEqual(scoped[0]["kind"], "competition_ended")
        reopen = lifecycle.preview_competition_reopen(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=data["competition_revision"],
        )
        lifecycle.apply_competition_reopen(
            actor=self.actor,
            token=reopen["token"],
            internal_reason="PRIVATE",
            confirm_resets=True,
        )
        stage = next(
            s
            for s in self.client.get(self.url).data["stages"]
            if s["id"] == destination.pk
        )
        self.assertEqual(
            (stage["lifecycle_state"], stage["draw_state"]),
            ("RETIRED", "AWAITING_REPLACEMENT"),
        )


class SwissAvailabilityPublicTests(APITestCase):
    setUp = swiss_fixtures.SwissCommandTests.setUp
    _registration = swiss_fixtures.SwissCommandTests._registration
    _competition = swiss_fixtures.SwissCommandTests._competition
    _swiss = swiss_fixtures.SwissCommandTests._swiss
    _elimination = swiss_fixtures.SwissCommandTests._elimination
    _revision = swiss_fixtures.SwissCommandTests._revision
    _draw = swiss_fixtures.SwissCommandTests._draw

    def test_swiss_competitive_status_is_separate_from_availability(self):
        draw = self._draw(4)
        tournament = self.division.tournament
        tournament.is_published = True
        tournament.save(update_fields=["is_published"])
        entrant = draw.entries.first().entrant
        preview = lifecycle.preview_entrant_transition(
            actor=self.actor,
            entrant_id=entrant.pk,
            expected_revision=self._revision(),
            status="DISQUALIFIED",
        )
        lifecycle.apply_entrant_transition(
            actor=self.actor,
            token=preview["token"],
            internal_reason="PRIVATE",
            confirm_resets=True,
        )
        data = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        ).data
        row = next(
            row
            for row in data["stages"][0]["swiss_standings"]
            if row["entry"]["status"] == "DISQUALIFIED"
        )
        self.assertIn(row["status"], ("ACTIVE", "QUALIFIED", "ELIMINATED"))
        self.assertEqual(row["entry"]["status"], "DISQUALIFIED")
