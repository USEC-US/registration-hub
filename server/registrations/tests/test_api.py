from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.tests.factories import create_account
from registrations.models import PaymentAttempt, Registration
from tournaments.models import Game, Tournament, TournamentGame

from .images import payment_image


@override_settings(ROOT_URLCONF="config.urls", DEBUG=True, TURNSTILE_SECRET_KEY="")
class RegistrationOwnershipApiTests(APITestCase):
    def setUp(self):
        from .payment_settings import configure_test_payments

        configure_test_payments()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
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
            main_roster_size=1,
            substitute_limit=0,
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
            "submitter_role": "captain",
            "contact_facebook_snapshot": "fb/me",
            "contact_phone_snapshot": "0900000000",
            "members": [
                {
                    "gamer_tag_snapshot": "captain",
                    "first_name_snapshot": "Player",
                    "last_name_snapshot": "Example",
                    "date_of_birth_snapshot": "2005-01-01",
                    "student_id_snapshot": "0012345",
                    "institution_label": "HCMUS",
                    "is_captain": True,
                    "display_order": 1,
                }
            ],
        }

    def test_payment_requires_a_valid_bounded_image(self):
        self.client.force_authenticate(user=self.owner)
        for proof in (
            None,
            SimpleUploadedFile("proof.jpg", b"not an image", content_type="image/jpeg"),
            SimpleUploadedFile(
                "proof.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>'
            ),
            SimpleUploadedFile("proof.png", b"x" * (10 * 1024 * 1024 + 1)),
            payment_image("GIF"),
        ):
            with self.subTest(proof=getattr(proof, "name", None)):
                payload = {
                    "amount": "50000.00",
                    "currency": "VND",
                    "reference": "BANK123",
                }
                if proof is not None:
                    payload["proof_file"] = proof
                response = self.client.post(
                    f"/api/registrations/{self.registration.pk}/payment-attempts/",
                    payload,
                    format="multipart",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("proof_file", response.data)
        self.assertFalse(self.registration.payment_attempts.exists())

    def test_payment_accepts_supported_images(self):
        self.client.force_authenticate(user=self.owner)
        for format in ("JPEG", "PNG", "WEBP"):
            with self.subTest(format=format):
                response = self.client.post(
                    f"/api/registrations/{self.registration.pk}/payment-attempts/",
                    {
                        "amount": "50000.00",
                        "currency": "VND",
                        "proof_file": payment_image(format),
                    },
                    format="multipart",
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertNotIn("proof_file", response.data)
                attempt = PaymentAttempt.objects.get(pk=response.data["id"])
                proof = self.client.get(attempt.proof_file.url)
                self.assertEqual(proof.status_code, 200)
                self.assertEqual(proof["Content-Type"], f"image/{format.lower()}")
                self.assertTrue(proof["Content-Disposition"].startswith("inline;"))
                if proof.streaming:
                    self.assertTrue(b"".join(proof.streaming_content))

    def test_payment_image_download_requires_owner_or_organizer(self):
        from django.contrib.auth.models import Group, Permission

        from registrations.services import submit_payment_attempt

        attempt = submit_payment_attempt(
            actor=self.owner,
            registration_id=self.registration.pk,
            amount=Decimal("50000.00"),
            currency="VND",
            proof_file=payment_image(),
        )
        url = attempt.proof_file.url
        response = self.client.get(url)
        self.assertIn(response.status_code, (401, 403))
        if response.streaming:
            self.assertTrue(b"".join(response.streaming_content))

        self.client.force_authenticate(self.other_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        if response.streaming:
            self.assertTrue(b"".join(response.streaming_content))
        self.client.force_authenticate(self.owner)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        if response.streaming:
            self.assertTrue(b"".join(response.streaming_content))
        self.client.force_authenticate(user=None)
        self.other_user.is_staff = True
        self.other_user.save(update_fields=["is_staff"])
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.other_user.groups.add(Group.objects.get_or_create(name="Organizers")[0])
        self.other_user.user_permissions.add(
            Permission.objects.get(codename="view_paymentattempt")
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        if response.streaming:
            self.assertTrue(b"".join(response.streaming_content))

    def test_legacy_non_raster_proof_stays_a_download(self):
        for filename in ("legacy.svg", "fake.png"):
            with self.subTest(filename=filename):
                attempt = PaymentAttempt.objects.create(
                    registration=self.registration,
                    method=PaymentAttempt.Method.MANUAL_PROOF,
                    amount="50000.00",
                    currency="VND",
                    proof_file=SimpleUploadedFile(
                        filename, b"<svg></svg>", content_type="image/svg+xml"
                    ),
                )
                self.client.force_authenticate(self.owner)
                response = self.client.get(attempt.proof_file.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/octet-stream")
                self.assertTrue(
                    response["Content-Disposition"].startswith("attachment;")
                )
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                if response.streaming:
                    self.assertTrue(b"".join(response.streaming_content))

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
        self.assertNotIn("reference", detail_response.data)
        self.assertTrue(
            all(
                "reference" not in attempt
                for attempt in detail_response.data["payment_attempts"]
            )
        )
        self.assertEqual(detail_response.data["payment_reference"], "")
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
            "proof_file": payment_image(),
            "turnstile_token": "debug-token",
        }
        self.client.post(
            f"/api/registrations/{self.registration.pk}/payment-attempts/",
            payment_payload,
            format="multipart",
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
        self.assertEqual(registration.members.get().user, self.owner)

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
            {"amount": "50000.00", "currency": "VND", "proof_file": payment_image()},
            format="multipart",
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
