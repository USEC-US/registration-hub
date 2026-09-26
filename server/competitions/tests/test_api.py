from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.tests.factories import create_account
from competitions.commands import (
    configure_elimination,
    create_competition,
    publish_draw,
    save_elimination_draw,
    select_entrants,
)
from competitions.models import Match
from registrations.models import Registration, RegistrationMember
from tournaments.models import Game, Tournament, TournamentGame


class PublicCompetitionApiTests(APITestCase):
    def setUp(self):
        self.actor = create_account(
            email="private-organizer@example.com",
            password="strong-password",
            first_name="Private",
            last_name="Organizer",
            is_staff=True,
            is_superuser=True,
        )
        game = Game.objects.create(name="Chess", slug="chess")
        self.tournament = Tournament.objects.create(
            name="Public Cup", slug="public-cup", is_published=True
        )
        self.division = TournamentGame.objects.create(
            tournament=self.tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        registrations = [self._registration(index) for index in range(1, 5)]
        self.competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        self.stage = configure_elimination(
            format="SINGLE_ELIMINATION",
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            name="Final bracket",
            default_series_length=3,
        )
        self.competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[item.pk for item in registrations],
        )
        self.competition.refresh_from_db()
        self.draw = save_elimination_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            entrant_order=[item.pk for item in entrants],
        )

    def _registration(self, index: int) -> Registration:
        registration = Registration.objects.create(
            tournament_game=self.division,
            status=Registration.Status.APPROVED,
            contact_phone_snapshot=f"PRIVATE-PHONE-{index}",
            fee_amount_snapshot="0.00",
            fee_currency_snapshot="VND",
        )
        RegistrationMember.objects.create(
            registration=registration,
            gamer_tag_snapshot=f"Public Player {index}",
            first_name_snapshot=f"PRIVATE-FIRST-{index}",
            last_name_snapshot=f"PRIVATE-LAST-{index}",
            student_id_snapshot=f"PRIVATE-STUDENT-{index}",
            is_captain=True,
            display_order=1,
        )
        return registration

    def _publish(self):
        self.competition.refresh_from_db()
        publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()

    def _double_elimination(self):
        self.competition.refresh_from_db()
        configure_elimination(
            format="DOUBLE_ELIMINATION",
            grand_final_policy="RESET",
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            name="Double bracket",
            default_series_length=3,
        )
        self.competition.refresh_from_db()
        draw = save_elimination_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            entrant_order=list(
                self.competition.entrants.order_by("pk").values_list("pk", flat=True)
            ),
        )
        self.stage.refresh_from_db()
        return draw

    def test_unpublished_competition_returns_404(self):
        response = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_overview_returns_published_bracket_with_public_fields_only(self):
        self._publish()

        response = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["competition_revision"], self.competition.revision
        )
        self.assertEqual(response.data["stages"][0]["name"], "Final bracket")
        self.assertEqual(response.data["stages"][0]["grand_final_policy"], "")
        self.assertEqual(
            response.data["stages"][0]["rounds"][0]["matches"][0]["code"],
            f"C{self.competition.pk}-D1-R1-M1",
        )
        rendered = response.rendered_content.decode()
        self.assertNotIn("PRIVATE-", rendered)
        self.assertNotIn(self.actor.email, rendered)

    def test_double_elimination_publishes_routing_and_conditional_reset(self):
        old_match = self.draw.rounds.get(number=1).matches.get(number=1)
        draw = self._double_elimination()
        self._publish()

        response = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stage = response.data["stages"][0]
        self.assertEqual(stage["format"], "DOUBLE_ELIMINATION")
        self.assertEqual(stage["grand_final_policy"], "RESET")
        self.assertEqual(
            {round_["section"] for round_ in stage["rounds"]},
            {"UPPER", "LOWER", "FINALS"},
        )
        sourced_slots = [
            slot
            for round_ in stage["rounds"]
            for match in round_["matches"]
            for slot in match["slots"]
            if slot["source_match_id"] is not None
        ]
        self.assertEqual(
            {slot["source_outcome"] for slot in sourced_slots}, {"WINNER", "LOSER"}
        )
        published_match_ids = {
            match["id"] for round_ in stage["rounds"] for match in round_["matches"]
        }
        self.assertTrue(
            all(
                slot["source_match_id"] in published_match_ids for slot in sourced_slots
            )
        )
        reset = next(
            match
            for round_ in stage["rounds"]
            if round_["section"] == "FINALS" and round_["number"] == 2
            for match in round_["matches"]
        )
        self.assertEqual(reset["status"], "CONDITIONAL")
        self.assertEqual(
            self.client.get(f"/api/competition-matches/{old_match.pk}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        current_match = Match.objects.filter(round__draw=draw).first()
        self.assertEqual(
            self.client.get(
                f"/api/competition-matches/{current_match.pk}/"
            ).status_code,
            status.HTTP_200_OK,
        )

    def test_public_correction_change_allowlists_nested_impact(self):
        self._publish()
        match = self.draw.rounds.get(number=1).matches.get(number=1)
        snapshot = {
            "match_id": match.pk,
            "match_code": match.code,
            "status": "FINAL",
            "outcome": "PLAYED",
            "side_one": "Public Player 1",
            "side_two": "Public Player 2",
            "side_one_score": 2,
            "side_two_score": 0,
            "winner": "Public Player 1",
            "applied_series_length": 3,
            "started_at": "2026-09-27T01:00:00Z",
            "completed_at": "2026-09-27T01:10:00Z",
            "student_id": "PRIVATE-STUDENT",
        }
        change = self.competition.changes.get(revision=self.competition.revision)
        change.public_data = {
            "kind": "result_corrected",
            "match_id": match.pk,
            "match_code": match.code,
            "before": snapshot,
            "after": {**snapshot, "side_one_score": 0, "side_two_score": 2},
            "reset_matches": [snapshot],
            "reset_final_changes": [
                {
                    "match_id": match.pk,
                    "match_code": match.code,
                    "before": "CONDITIONAL",
                    "after": "ACTIVE",
                    "internal_reason": "PRIVATE-REASON",
                }
            ],
            "actor_email": self.actor.email,
        }
        change.save(update_fields=("public_data",))

        response = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/changes/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data["results"][0]
        self.assertEqual(result["before"]["outcome"], "PLAYED")
        self.assertEqual(result["after"]["side_two_score"], 2)
        self.assertEqual(result["reset_matches"][0]["match_code"], match.code)
        self.assertEqual(
            result["reset_final_changes"][0],
            {
                "match_id": match.pk,
                "match_code": match.code,
                "before": "CONDITIONAL",
                "after": "ACTIVE",
            },
        )
        rendered = response.rendered_content.decode()
        self.assertNotIn("PRIVATE-", rendered)
        self.assertNotIn(self.actor.email, rendered)

    def test_stage_round_match_and_changes_include_same_revision(self):
        self._publish()
        match = self.draw.rounds.get(number=1).matches.get(number=1)
        self.competition.changes.filter(revision=self.competition.revision).update(
            internal_reason="PRIVATE-INTERNAL-NOTE"
        )

        urls = (
            f"/api/competition-stages/{self.stage.pk}/",
            f"/api/competition-rounds/{match.round_id}/",
            f"/api/competition-matches/{match.pk}/",
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    response.data["competition_revision"], self.competition.revision
                )

        changes = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/changes/"
        )
        self.assertEqual(changes.status_code, status.HTTP_200_OK)
        self.assertEqual(
            changes.data["competition_revision"], self.competition.revision
        )
        rendered = changes.rendered_content.decode()
        self.assertNotIn("PRIVATE-INTERNAL-NOTE", rendered)
        self.assertNotIn(self.actor.email, rendered)

    def test_unpublishing_parent_hides_every_public_endpoint(self):
        self._publish()
        match = self.draw.rounds.get(number=1).matches.get(number=1)
        self.tournament.is_published = False
        self.tournament.save(update_fields=("is_published",))

        for url in (
            f"/api/tournament-games/{self.division.pk}/competition/",
            f"/api/competition-stages/{self.stage.pk}/",
            f"/api/competition-rounds/{match.round_id}/",
            f"/api/competition-matches/{match.pk}/",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code, status.HTTP_404_NOT_FOUND
                )
