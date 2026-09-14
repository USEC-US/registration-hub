import json
from unittest.mock import patch

from django.test import override_settings
from django.core.cache import cache
from rest_framework.test import APITestCase

from . import test_guest_submission
from .images import payment_image


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
class PaymentReferenceTests(APITestCase):
    setUp = test_guest_submission.GuestSubmissionTests.setUp
    _create_registration = (
        test_guest_submission.GuestSubmissionTests._create_registration
    )
    payload = test_guest_submission.GuestSubmissionTests.payload
    post = test_guest_submission.GuestSubmissionTests.post

    def reserve(self, **extra):
        cache.clear()
        return self.client.post(
            "/api/payment-references/",
            {"tournament_game": self.tournament_game.pk, **extra},
            format="json",
        )

    def test_guest_reference_is_stable_private_and_consumed_once(self):
        response = self.reserve()
        self.assertEqual(response.status_code, 200, response.data)
        intent = response.data
        self.assertRegex(intent["reference"], r"^USEC[A-Z0-9]{10}$")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.reserve(token=intent["token"]).data, intent)
        payload = self.payload()
        payload["payment_intent_token"] = intent["token"]
        receipt = self.post(payload, payment_image())
        self.assertEqual(receipt.status_code, 201, receipt.data)
        self.assertEqual(receipt.data["payment_reference"], intent["reference"])
        self.assertNotIn("payment_intent_token", receipt.data)
        payload["members"][0]["gamer_tag_snapshot"] = "second-player"
        self.assertEqual(self.post(payload, payment_image()).status_code, 400)
        self.assertEqual(self.reserve(token=intent["token"]).status_code, 400)

    def test_unknown_tokens_and_fee_changes_do_not_replace_a_paid_reference(self):
        intent = self.reserve().data
        payload = self.payload()
        payload["payment_intent_token"] = "00000000-0000-0000-0000-000000000000"
        self.assertEqual(self.post(payload, payment_image()).status_code, 400)
        payload["payment_intent_token"] = intent["token"]
        self.tournament_game.fee_amount = 60000
        self.tournament_game.save()
        self.assertEqual(
            self.reserve(token=intent["token"]).data["reference"], intent["reference"]
        )
        response = self.post(payload, payment_image())
        self.assertEqual(response.status_code, 400)
        self.assertIn("payment_intent_token", response.data)

    def test_free_entries_cannot_reserve_a_reference(self):
        self.tournament_game.fee_amount = 0
        self.tournament_game.save()
        self.assertEqual(self.reserve().status_code, 400)

    def test_existing_payment_reference_endpoint_requires_ownership(self):
        self.client.force_authenticate(self.owner)
        registration = self._create_registration(self.owner)
        url = f"/api/registrations/{registration.pk}/payment-reference/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.post(url).data, response.data)
        self.client.force_authenticate(None)
        self.assertIn(self.client.post(url).status_code, (401, 403))

    def test_paid_guest_cannot_submit_without_an_issued_reference(self):
        response = self.client.post(
            "/api/registrations/submit/",
            {"payload": json.dumps(self.payload()), "proof_file": payment_image()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("payment_intent_token", response.data)

    def test_reference_collision_retries_without_reusing_an_existing_code(self):
        from registrations.payments import create_payment_intent

        with patch("registrations.payments.secrets.choice", return_value="A"):
            original = create_payment_intent(tournament_game=self.tournament_game)
        with patch(
            "registrations.payments.secrets.choice",
            side_effect=list("A" * 10 + "B" * 10),
        ):
            replacement = create_payment_intent(tournament_game=self.tournament_game)
        self.assertEqual(original.reference, "USEC" + "A" * 10)
        self.assertEqual(replacement.reference, "USEC" + "B" * 10)
        self.assertNotEqual(original.pk, replacement.pk)
