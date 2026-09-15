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
        self.assertNotIn("reference", intent)
        self.assertIn("transfer_content_template", intent)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.reserve(token=intent["token"]).data, intent)
        payload = self.payload()
        payload["payment_intent_token"] = intent["token"]
        receipt = self.post(payload, payment_image())
        self.assertEqual(receipt.status_code, 201, receipt.data)
        self.assertRegex(receipt.data["payment_reference"], r"^USEC[A-Z0-9]{10}$")
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
        self.assertEqual(self.reserve(token=intent["token"]).data, intent)
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

    def test_explicit_receiving_settings_are_snapshotted_and_stay_stable(self):
        from registrations.models import PaymentSettings
        from registrations.payments import create_payment_intent

        PaymentSettings.objects.all().delete()
        settings = PaymentSettings.objects.create(
            enabled=True,
            bank_name="VietinBank",
            bank_bin="970415",
            account_number="0011001932418",
            account_holder="HCMUSEC",
        )

        registration = self._create_registration(self.owner)
        intent = create_payment_intent(
            tournament_game=self.tournament_game,
            registration=registration,
            payment_settings=settings,
        )
        settings.bank_name = "Changed Bank"
        settings.bank_bin = "970436"
        settings.account_number = "0000000001"
        settings.account_holder = "CHANGED HOLDER"
        settings.save()
        intent.refresh_from_db()

        self.assertEqual(intent.bank_name_snapshot, "VietinBank")
        self.assertEqual(intent.bank_bin_snapshot, "970415")
        self.assertEqual(intent.account_number_snapshot, "0011001932418")
        self.assertEqual(intent.account_holder_snapshot, "HCMUSEC")

    def test_legacy_intent_call_does_not_invent_destination_snapshot(self):
        from registrations.payments import create_payment_intent

        intent = create_payment_intent(tournament_game=self.tournament_game)

        self.assertEqual(intent.bank_name_snapshot, "")
        self.assertEqual(intent.bank_bin_snapshot, "")
        self.assertEqual(intent.account_number_snapshot, "")
        self.assertEqual(intent.account_holder_snapshot, "")

    def test_reference_visible_after_submission_even_while_payment_pending(self):
        from registrations.models import Registration

        self.client.force_authenticate(self.owner)
        response = self.post(self.payload(), payment_image())
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertEqual(
            response.data["payment_reference"], registration.payment_intent.reference
        )
        self.assertEqual(response.data["payment_attempts"][0]["status"], "PENDING")
        instructions = self.client.post(
            f"/api/registrations/{registration.pk}/payment-instructions/"
        )
        self.assertEqual(instructions.status_code, 200, instructions.data)
        self.assertNotIn("reference", instructions.data)
        self.assertEqual(
            instructions.data["transfer_content"],
            registration.payment_intent.transfer_content,
        )

    def test_transfer_template_is_snapshotted_and_accents_removed(self):
        from registrations.models import Registration

        tournament = self.tournament_game.tournament
        tournament.transfer_content_template = (
            "{participant} thanh toán lệ phí cho giải đấu Đấu Trường XV"
        )
        tournament.save()
        intent = self.reserve().data
        tournament.transfer_content_template = "Changed {participant}"
        tournament.save()
        self.assertEqual(self.reserve(token=intent["token"]).data, intent)
        payload = self.payload()
        payload["members"][0]["gamer_tag_snapshot"] = "Đặng Thắng#VN"
        payload["payment_intent_token"] = intent["token"]
        response = self.post(payload, payment_image())
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertEqual(
            registration.payment_intent.transfer_content,
            "Dang Thang#VN thanh toan le phi cho giai dau Dau Truong XV",
        )
        self.assertNotIn(
            registration.payment_intent.reference,
            registration.payment_intent.transfer_content,
        )

    def test_transfer_content_over_limit_is_rejected_without_claiming_intent(self):
        from registrations.models import PaymentIntent

        tournament = self.tournament_game.tournament
        tournament.transfer_content_template = "{participant} paid"
        tournament.transfer_content_limit = 10
        tournament.save()
        intent = self.reserve().data
        payload = self.payload()
        payload["payment_intent_token"] = intent["token"]
        response = self.post(payload, payment_image())
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("transfer_content", response.data)
        self.assertIsNone(
            PaymentIntent.objects.get(token=intent["token"]).registration_id
        )

    def test_team_transfer_uses_normalized_tag_not_team_name(self):
        from registrations.models import Registration

        payload = test_guest_submission.GuestSubmissionTests.team_payload(self)
        self.tournament_game.fee_amount = 50000
        self.tournament_game.save()
        payload["team_name"] = "Full Team Name"
        payload["team_tag"] = "abc"
        payload["payment_intent_token"] = self.reserve().data["token"]
        response = self.post(payload, payment_image())
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertEqual(
            registration.payment_intent.transfer_content, "ABC thanh toan le phi Summer"
        )

    def test_transfer_instructions_require_ownership_and_do_not_rewrite_legacy_data(
        self,
    ):
        from registrations.models import PaymentIntent

        registration = self._create_registration(self.owner)
        intent = PaymentIntent.objects.create(
            registration=registration,
            tournament_game=self.tournament_game,
            amount=50000,
            currency="VND",
            reference="USECLEGACY1234",
        )
        url = f"/api/registrations/{registration.pk}/payment-instructions/"
        self.assertIn(self.client.post(url).status_code, (401, 403))
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_authenticate(self.owner)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["transfer_content"], "")
        intent.refresh_from_db()
        self.assertEqual(intent.transfer_content_template, "")

    def test_legacy_unsubmitted_session_is_not_silently_replaced(self):
        from registrations.models import PaymentIntent

        intent = PaymentIntent.objects.create(
            tournament_game=self.tournament_game,
            amount=50000,
            currency="VND",
            reference="USECLEGACY1234",
        )
        response = self.reserve(token=str(intent.token))
        self.assertEqual(response.status_code, 400)
        self.assertIn("transfer_content", response.data)
        self.assertEqual(response.data["code"], "legacy_payment_session")
        self.assertEqual(PaymentIntent.objects.count(), 1)
        replacement = self.reserve()
        self.assertEqual(replacement.status_code, 200, replacement.data)
        self.assertNotEqual(replacement.data["token"], str(intent.token))
        intent.refresh_from_db()
        self.assertEqual(intent.transfer_content_template, "")
        self.assertEqual(intent.reference, "USECLEGACY1234")
        self.assertIsNone(intent.registration_id)
        self.assertEqual(PaymentIntent.objects.count(), 2)
