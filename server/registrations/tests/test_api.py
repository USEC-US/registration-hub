from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from registrations.models import Registration
from tournaments.models import Game, Tournament, TournamentGame


@override_settings(ROOT_URLCONF="config.urls")
class RegistrationOwnershipApiTests(APITestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            email="owner@example.com", password="strong-password"
        )
        self.other_user = get_user_model().objects.create_user(
            email="other@example.com", password="strong-password"
        )
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(name="Summer", slug="summer")
        self.tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            team_size_min=1,
            team_size_max=1,
            registration_opens_at=timezone.now() - timedelta(minutes=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount=Decimal("50000.00"),
            fee_currency="VND",
        )
        self.registration = self._create_registration(self.owner)
        self._create_registration(self.other_user)

    def _create_registration(self, owner):
        return Registration.objects.create(
            tournament_game=self.tournament_game,
            submitted_by=owner,
            team_name="",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=Decimal("50000.00"),
            fee_currency_snapshot="VND",
        )

    def _submission_payload(self):
        return {
            "tournament_game": self.tournament_game.pk,
            "team_name": "",
            "members": [
                {
                    "gamer_tag_snapshot": "captain",
                    "school_snapshot": "HCMUS",
                    "is_captain": True,
                    "display_order": 1,
                }
            ],
        }

    def test_unauthenticated_list_and_detail_are_not_available(self):
        list_response = self.client.get("/api/registrations/")
        detail_response = self.client.get(
            f"/api/registrations/{self.registration.pk}/"
        )

        self.assertIn(
            list_response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )
        self.assertIn(
            detail_response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_owner_lists_and_retrieves_only_own_registration(self):
        self.client.force_authenticate(user=self.owner)

        list_response = self.client.get("/api/registrations/")
        detail_response = self.client.get(f"/api/registrations/{self.registration.pk}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in list_response.data}, {self.registration.pk}
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertNotIn("submitted_by", detail_response.data)
        self.assertNotIn("payment_attempts", detail_response.data)

    def test_other_user_gets_404_for_a_foreign_registration(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(f"/api/registrations/{self.registration.pk}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_sets_the_owner_from_request_user(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            "/api/registrations/submit/", self._submission_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertEqual(registration.submitted_by, self.owner)
        self.assertIsNone(registration.members.get().user)

    def test_service_validation_errors_become_http_400(self):
        self.client.force_authenticate(user=self.owner)
        invalid_submission = self._submission_payload()
        invalid_submission["team_name"] = "not-valid-for-a-solo-game"

        submission_response = self.client.post(
            "/api/registrations/submit/", invalid_submission, format="json"
        )
        payment_response = self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            {"amount": "1.00", "currency": "VND", "reference": "wrong-amount"},
            format="json",
        )

        self.assertEqual(submission_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(payment_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_rejects_client_supplied_owner_or_player_account_fields(self):
        self.client.force_authenticate(user=self.owner)
        owner_payload = self._submission_payload()
        owner_payload["submitted_by"] = self.other_user.pk
        member_payload = self._submission_payload()
        member_payload["members"][0]["user_id"] = self.other_user.pk

        owner_response = self.client.post(
            "/api/registrations/submit/", owner_payload, format="json"
        )
        member_response = self.client.post(
            "/api/registrations/submit/", member_payload, format="json"
        )

        self.assertEqual(owner_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("submitted_by", owner_response.data)
        self.assertEqual(member_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("members", member_response.data)

    def test_other_user_cannot_add_a_payment_attempt_to_foreign_registration(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            {"amount": "50000.00", "currency": "VND", "reference": "transfer-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
