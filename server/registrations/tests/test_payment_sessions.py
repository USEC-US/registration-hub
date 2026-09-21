from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from registrations.models import PaymentAttempt, PaymentSettings, Registration
from . import test_guest_submission
from .images import payment_image


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
class PaymentSessionTests(APITestCase):
    setUp = test_guest_submission.GuestSubmissionTests.setUp
    _create_registration = (
        test_guest_submission.GuestSubmissionTests._create_registration
    )
    payload = test_guest_submission.GuestSubmissionTests.payload
    secret = "ab" * 32

    def create_saved(self):
        response = self.client.post(
            "/api/registrations/submit/",
            self.payload(),
            format="json",
            HTTP_X_REGISTRATION_ACCESS=self.secret,
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Registration.objects.get(pk=response.data["id"])

    def session(self, registration, **headers):
        return self.client.post(
            f"/api/registrations/{registration.pk}/payment-session/",
            {},
            format="json",
            **headers,
        )

    def private_session(self, registration):
        return self.session(registration, HTTP_X_REGISTRATION_ACCESS=self.secret)

    def test_private_session_has_current_tournament_slug_for_retry(self):
        registration = self.create_saved()
        self.assertEqual(
            self.private_session(registration).data["tournament_slug"],
            self.tournament_game.tournament.slug,
        )

    def test_only_private_session_exposes_saved_identity(self):
        registration = self.create_saved()
        response = self.private_session(registration)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["saved_submission"]["members"][0]["first_name_snapshot"],
            "Player",
        )
        self.assertEqual(response.data["institution_labels"], {"1": "New school"})
        self.assertNotIn("first_name_snapshot", str(response.data["registration"]))
        self.assertNotIn("contact_phone_snapshot", response.data["registration"])
        self.assertNotIn("payment_intent_token", response.data["saved_submission"])
        instructions = response.data["instructions"]
        self.assertTrue(instructions["qr_payload"])
        self.assertTrue(
            instructions["qr_png_data_url"].startswith("data:image/png;base64,")
        )
        original = dict(instructions)
        settings = PaymentSettings.objects.get()
        settings.account_number = "999999"
        settings.save()
        self.assertEqual(
            self.private_session(registration).data["instructions"], original
        )

    def test_known_guest_id_without_credential_is_not_authority(self):
        registration = self.create_saved()
        for headers in (
            {},
            {"HTTP_X_REGISTRATION_ACCESS": "cd" * 32},
            {"HTTP_X_REGISTRATION_ACCESS": "USEC123"},
        ):
            response = self.session(registration, **headers)
            self.assertIn(response.status_code, (400, 404))
            self.assertEqual(response["Cache-Control"], "private, no-store")
        response = self.session(
            self.registration, HTTP_X_REGISTRATION_ACCESS=self.secret
        )
        self.assertEqual(response.status_code, 404)
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.session(self.registration).status_code, 200)
        self.assertEqual(
            self.session(
                self.registration, HTTP_X_REGISTRATION_ACCESS=self.secret
            ).status_code,
            404,
        )
        self.assertEqual(self.session(registration).status_code, 404)

    def test_access_survives_unpublish_but_new_proof_is_blocked(self):
        registration = self.create_saved()
        tournament = self.tournament_game.tournament
        tournament.is_published = False
        tournament.save()
        response = self.private_session(registration)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_upload_proof"])
        self.assertIsNone(response.data["instructions"]["qr_payload"])
        proof = self.client.post(
            f"/api/registrations/{registration.pk}/payment-proof/",
            {"proof_file": payment_image()},
            format="multipart",
            HTTP_X_REGISTRATION_ACCESS=self.secret,
        )
        self.assertEqual(proof.status_code, 400)
        self.assertEqual(proof["Cache-Control"], "private, no-store")

    def test_proof_is_derived_from_saved_amount_and_is_not_downloadable_by_guest(self):
        registration = self.create_saved()
        response = self.client.post(
            f"/api/registrations/{registration.pk}/payment-proof/",
            {"proof_file": payment_image(), "reference": "BANK"},
            format="multipart",
            HTTP_X_REGISTRATION_ACCESS=self.secret,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["payment_state"], "PENDING")
        self.assertFalse(response.data["can_upload_proof"])
        self.assertIsNone(response.data["instructions"]["qr_payload"])
        attempt = registration.payment_attempts.get()
        self.assertEqual(attempt.amount, registration.fee_amount_snapshot)
        self.assertNotIn("proof_file", str(response.data))
        download = self.client.get(
            attempt.proof_file.url, HTTP_X_REGISTRATION_ACCESS=self.secret
        )
        self.assertIn(download.status_code, (401, 403))
        second = self.client.post(
            f"/api/registrations/{registration.pk}/payment-proof/",
            {"proof_file": payment_image()},
            format="multipart",
            HTTP_X_REGISTRATION_ACCESS=self.secret,
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(registration.payment_attempts.count(), 1)

    def test_expired_rejected_verified_and_free_states_have_no_actionable_qr(self):
        registration = self.create_saved()
        registration.payment_due_at = timezone.now() - timedelta(seconds=1)
        registration.save()
        response = self.private_session(registration)
        self.assertTrue(response.data["expired"])
        self.assertTrue(response.data["can_retry_registration"])
        self.assertFalse(response.data["can_upload_proof"])
        self.assertIsNone(response.data["instructions"]["qr_payload"])
        registration.status = Registration.Status.REJECTED
        registration.save()
        self.assertFalse(self.private_session(registration).data["can_upload_proof"])
        registration.status = Registration.Status.SUBMITTED
        registration.save()
        PaymentAttempt.objects.create(
            registration=registration,
            amount=registration.fee_amount_snapshot,
            currency="VND",
            status="VERIFIED",
            method="MANUAL_PROOF",
        )
        response = self.private_session(registration)
        self.assertFalse(response.data["expired"])
        self.assertEqual(response.data["payment_state"], "VERIFIED")
        self.assertIsNone(response.data["instructions"]["qr_payload"])
        registration.fee_amount_snapshot = Decimal("0")
        registration.save()
        response = self.private_session(registration)
        self.assertEqual(response.data["payment_state"], "NOT_REQUIRED")
        self.assertIsNone(response.data["instructions"])

    def test_rejected_proof_note_and_legacy_session(self):
        registration = self.create_saved()
        PaymentAttempt.objects.create(
            registration=registration,
            amount=registration.fee_amount_snapshot,
            currency="VND",
            status="REJECTED",
            method="MANUAL_PROOF",
            review_note="Wrong receipt",
            reviewed_at=timezone.now(),
        )
        response = self.private_session(registration)
        self.assertEqual(response.data["replacement_note"], "Wrong receipt")
        self.assertTrue(response.data["can_upload_proof"])
        self.client.force_authenticate(user=self.owner)
        response = self.session(self.registration)
        self.assertIsNone(response.data["payment_due_at"])
        self.assertIsNone(response.data["instructions"])
        self.assertTrue(response.data["can_upload_proof"])

    def test_public_division_has_payment_availability_and_hold(self):
        from tournaments.serializers import PublicTournamentGameSerializer

        data = PublicTournamentGameSerializer(self.tournament_game).data
        self.assertTrue(data["payment_available"])
        self.assertEqual(data["payment_hold_minutes"], 60)
        PaymentSettings.objects.update(enabled=False)
        self.assertFalse(
            PublicTournamentGameSerializer(self.tournament_game).data[
                "payment_available"
            ]
        )
        self.tournament_game.fee_amount = 0
        self.assertTrue(
            PublicTournamentGameSerializer(self.tournament_game).data[
                "payment_available"
            ]
        )

    def test_private_endpoints_are_throttled_and_cors_allows_header(self):
        from django.conf import settings
        from registrations.private_views import PrivateRegistrationThrottle
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        self.assertIn("x-registration-access", settings.CORS_ALLOW_HEADERS)
        from unittest.mock import patch

        with patch.object(PrivateRegistrationThrottle, "rate", "1/hour"):
            self.client.post(
                "/api/registrations/resume/", {}, HTTP_X_REGISTRATION_ACCESS=self.secret
            )
            response = self.client.post(
                "/api/registrations/resume/", {}, HTTP_X_REGISTRATION_ACCESS=self.secret
            )
        self.assertEqual(response.status_code, 429)
        self.assertIn("no-store", response["Cache-Control"])

    def test_raw_boolean_and_anonymous_user_cannot_authorize_service_upload(self):
        from django.contrib.auth.models import AnonymousUser
        from django.core.exceptions import PermissionDenied
        from registrations.services import submit_payment_attempt

        registration = self.create_saved()
        for access in (None, True):
            with self.assertRaises(PermissionDenied):
                submit_payment_attempt(
                    actor=AnonymousUser(),
                    registration_id=registration.pk,
                    amount=registration.fee_amount_snapshot,
                    currency="VND",
                    proof_file=payment_image(),
                    registration_access=access,
                )
        self.assertFalse(registration.payment_attempts.exists())

    def test_proof_authentication_errors_are_private(self):
        response = self.client.get("/media/payment-proofs/unknown.png")
        self.assertIn(response.status_code, (401, 403))
        self.assertIn("no-store", response.get("Cache-Control", ""))
