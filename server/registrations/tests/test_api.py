from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.tests.factories import create_account

from registrations.models import Registration
from tournaments.models import Game, Tournament, TournamentGame

@override_settings(ROOT_URLCONF="config.urls", DEBUG=True, TURNSTILE_SECRET_KEY="")
class RegistrationOwnershipApiTests(APITestCase):
    def setUp(self):
        self.owner = create_account(
            email="owner@example.com",
            password="strong-password",
            first_name="Owner",
            last_name="Player",
        )
        self.other_user = create_account(
            email="other@example.com",
            password="strong-password",
            first_name="Other",
            last_name="Player",
        )
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(
            name="Summer", slug="summer", is_published=True
        )
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
        detail_response = self.client.get(f"/api/registrations/{self.registration.pk}/")

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
        self.assertIn("payment_attempts", detail_response.data)
        self.assertNotIn("proof_file", str(detail_response.data))
        self.assertNotIn("reference", str(detail_response.data))
        self.assertNotIn("review_note", str(detail_response.data))

    def test_unpublished_tournament_registrations_are_hidden(self):
        self.client.force_authenticate(user=self.owner)
        tournament = self.tournament_game.tournament
        tournament.is_published = False
        tournament.save(update_fields=("is_published",))

        list_response = self.client.get("/api/registrations/")
        detail_response = self.client.get(f"/api/registrations/{self.registration.pk}/")
        payment_response = self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            {"amount": "50000.00", "currency": "VND", "reference": "hidden"},
            format="json",
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data, [])
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(payment_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_rejects_an_unpublished_tournament_game(self):
        self.client.force_authenticate(user=self.owner)
        tournament = self.tournament_game.tournament
        tournament.is_published = False
        tournament.save(update_fields=("is_published",))

        response = self.client.post(
            "/api/registrations/submit/", self._submission_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Registration.objects.count(), 2)

    def test_registration_detail_exposes_safe_own_payment_attempt_summary(self):
        self.client.force_authenticate(user=self.owner)
        payment_payload = {
            "amount": "50000.00",
            "currency": "VND",
            "reference": "transfer-123",
            "turnstile_token": "debug-token",
        }
        self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            payment_payload,
            format="json",
        )

        response = self.client.get(f"/api/registrations/{self.registration.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["payment_required"])
        self.assertEqual(len(response.data["payment_attempts"]), 1)
        self.assertEqual(response.data["payment_attempts"][0]["status"], "PENDING")
        self.assertNotIn("proof_file", response.data["payment_attempts"][0])
        self.assertNotIn("reference", response.data["payment_attempts"][0])
        self.assertNotIn("review_note", response.data["payment_attempts"][0])

    def test_other_user_gets_404_for_a_foreign_registration(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(f"/api/registrations/{self.registration.pk}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_sets_the_owner_from_request_user(self):
        self.client.force_authenticate(user=self.owner)
        payload = self._submission_payload()
        payload["turnstile_token"] = "debug-token"

        response = self.client.post(
            "/api/registrations/submit/", payload, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertEqual(registration.submitted_by, self.owner)
        self.assertIsNone(registration.members.get().user)

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_submit_requires_turnstile_outside_debug(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            "/api/registrations/submit/",
            self._submission_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("turnstile_token", response.data)

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_payment_attempt_requires_turnstile_outside_debug(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            {"amount": "50000.00", "currency": "VND", "reference": "BANK123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("turnstile_token", response.data)

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
