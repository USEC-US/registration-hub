from datetime import timedelta
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from . import test_guest_submission


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
class RegistrationAccessTests(APITestCase):
    setUp = test_guest_submission.GuestSubmissionTests.setUp
    _create_registration = (
        test_guest_submission.GuestSubmissionTests._create_registration
    )
    payload = test_guest_submission.GuestSubmissionTests.payload
    secret = "ab" * 32

    def submit(self, payload=None, secret=None):
        return self.client.post(
            "/api/registrations/submit/",
            payload or self.payload(),
            format="json",
            HTTP_X_REGISTRATION_ACCESS=secret or self.secret,
        )

    def test_guest_can_resume_committed_submission_without_id(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.data)
        resumed = self.client.post(
            "/api/registrations/resume/",
            {},
            format="json",
            HTTP_X_REGISTRATION_ACCESS=self.secret,
        )
        self.assertEqual(resumed.status_code, 200, resumed.data)
        self.assertEqual(resumed.data["registration"]["id"], response.data["id"])
        self.assertEqual(resumed.data["payment_state"], "UNPAID")
        self.assertNotIn(self.secret, str(resumed.data))
        self.assertIn("no-store", resumed["Cache-Control"])

    def test_replay_precedes_mutable_business_rules(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.tournament_game.registration_closes_at = timezone.now() - timedelta(
            seconds=1
        )
        self.tournament_game.main_roster_size = 4
        self.tournament_game.save()
        payload = dict(reversed(list(self.payload().items())))
        payload.update(
            team_tag="",
            manager_name_snapshot="",
            contact_email_snapshot="",
            contact_discord_snapshot="",
            turnstile_token="fresh",
        )
        payload["members"][0]["roster_role"] = "main"
        replay = self.submit(payload)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["id"], response.data["id"])
        self.assertEqual(replay.data["payment_due_at"], response.data["payment_due_at"])

    def test_changed_payload_or_actor_conflicts(self):
        self.assertEqual(self.submit().status_code, 201)
        payload = self.payload()
        payload["contact_phone_snapshot"] = "0909999999"
        self.assertEqual(self.submit(payload).status_code, 409)
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.submit().status_code, 409)

    def test_bad_credentials_are_private_errors(self):
        for secret in ("", "wrong", "AB" * 32, "cd" * 32):
            response = self.client.post(
                "/api/registrations/resume/",
                {},
                format="json",
                HTTP_X_REGISTRATION_ACCESS=secret,
            )
            self.assertIn(response.status_code, (400, 404))
            self.assertIn("no-store", response["Cache-Control"])

    def test_credential_hash_and_invalid_header_do_not_create_records(self):
        import hashlib
        from registrations.models import Registration, RegistrationAccess

        before = Registration.objects.count()
        for secret in ("x", "AB" * 32, "ab" * 31, "ab" * 32 + "\n"):
            self.assertEqual(self.submit(secret=secret).status_code, 400)
        self.assertEqual(Registration.objects.count(), before)
        response = self.submit()
        access = RegistrationAccess.objects.get(registration_id=response.data["id"])
        self.assertEqual(
            access.credential_hash, hashlib.sha256(self.secret.encode()).hexdigest()
        )
        self.assertNotIn(self.secret, str(access.__dict__))

    def test_retry_requires_fresh_challenge_but_resume_does_not(self):
        from unittest.mock import patch
        from config.turnstile import TurnstileVerificationResult

        self.assertEqual(self.submit().status_code, 201)
        with patch(
            "config.turnstile.verify_turnstile_token",
            return_value=TurnstileVerificationResult(
                success=False, error_codes=("timeout-or-duplicate",)
            ),
        ):
            response = self.submit()
            self.assertEqual(response.status_code, 400)
            self.assertIn("turnstile_token", response.data)
            response = self.client.post(
                "/api/registrations/resume/", {}, HTTP_X_REGISTRATION_ACCESS=self.secret
            )
            self.assertEqual(response.status_code, 200)

    def test_initial_multipart_proof_replay_binds_original_bytes_and_reference(self):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        from registrations.payments import create_payment_intent
        from registrations.models import PaymentAttempt
        from .images import payment_image

        payload = self.payload()
        payload["payment_intent_token"] = str(
            create_payment_intent(tournament_game=self.tournament_game).token
        )
        image = payment_image()
        original = image.read()

        def send(content, reference="BANK"):
            return self.client.post(
                "/api/registrations/submit/",
                {
                    "payload": json.dumps(payload),
                    "proof_file": SimpleUploadedFile(
                        "proof.png", content, content_type="image/png"
                    ),
                    "reference": reference,
                },
                format="multipart",
                HTTP_X_REGISTRATION_ACCESS=self.secret,
            )

        first = send(original)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(send(original).status_code, 200)
        self.assertEqual(send(original + b"changed").status_code, 409)
        self.assertEqual(send(original, "different").status_code, 409)
        self.assertEqual(
            PaymentAttempt.objects.filter(registration_id=first.data["id"]).count(), 1
        )

    def test_failed_configuration_rolls_back_custom_institution_and_access(self):
        from accounts.models import Institution
        from registrations.models import (
            PaymentSettings,
            Registration,
            RegistrationAccess,
        )

        before = Registration.objects.count(), Institution.objects.count()
        PaymentSettings.objects.update(enabled=False)
        response = self.submit()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            (Registration.objects.count(), Institution.objects.count()), before
        )
        self.assertFalse(RegistrationAccess.objects.exists())
        self.assertIn("no-store", response["Cache-Control"])

    def test_roster_default_student_id_and_member_order_are_canonical(self):
        from registrations.access import submission_digest

        payload = self.payload()
        del payload["members"][0]["student_id_snapshot"]
        digest = submission_digest(payload)
        payload["members"][0].update(student_id_snapshot="", roster_role="main")
        self.assertEqual(submission_digest(payload), digest)
        payload["members"].append(
            {**payload["members"][0], "display_order": 2, "gamer_tag_snapshot": "other"}
        )
        digest = submission_digest(payload)
        payload["members"].reverse()
        self.assertNotEqual(submission_digest(payload), digest)

    def test_identical_numeric_string_division_replays(self):
        payload = self.payload()
        payload["tournament_game"] = str(payload["tournament_game"])
        response = self.submit(payload)
        self.assertEqual(response.status_code, 201, response.data)
        replay = self.submit(payload)
        self.assertEqual(replay.status_code, 200, replay.data)

    def test_failed_initial_proof_save_rolls_back_access_and_file(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from django.conf import settings
        from registrations.models import (
            PaymentAttempt,
            RegistrationAccess,
            Registration,
        )
        from registrations.payments import create_payment_intent
        from .images import payment_image

        payload = self.payload()
        intent = create_payment_intent(tournament_game=self.tournament_game)
        payload["payment_intent_token"] = str(intent.token)
        original_save = PaymentAttempt.save

        def failing_save(attempt, *args, **kwargs):
            original_save(attempt, *args, **kwargs)
            raise RuntimeError("Simulated post-file failure")

        with (
            patch.object(PaymentAttempt, "save", failing_save),
            self.assertRaises(RuntimeError),
        ):
            self.client.post(
                "/api/registrations/submit/",
                {"payload": json.dumps(payload), "proof_file": payment_image()},
                format="multipart",
                HTTP_X_REGISTRATION_ACCESS=self.secret,
            )
        self.assertFalse(RegistrationAccess.objects.exists())
        self.assertEqual(Registration.objects.count(), 2)
        self.assertFalse(list(Path(settings.MEDIA_ROOT).rglob("*.png")))
        intent.refresh_from_db()
        self.assertIsNone(intent.registration_id)


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
class RegistrationAccessConcurrencyTests(TransactionTestCase):
    setUp = test_guest_submission.GuestSubmissionTests.setUp
    _create_registration = (
        test_guest_submission.GuestSubmissionTests._create_registration
    )
    payload = test_guest_submission.GuestSubmissionTests.payload

    def race(self, different_divisions=False):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        from rest_framework.test import APIClient
        from registrations.models import Registration, RegistrationAccess
        from tournaments.models import TournamentGame, Game

        payloads = [self.payload(), self.payload()]
        if different_divisions:
            game = Game.objects.create(name="Other", slug="other")
            other = TournamentGame.objects.create(
                tournament=self.tournament_game.tournament,
                game=game,
                main_roster_size=1,
                substitute_limit=0,
                registration_opens_at=self.tournament_game.registration_opens_at,
                registration_closes_at=self.tournament_game.registration_closes_at,
                fee_amount=self.tournament_game.fee_amount,
                fee_currency="VND",
            )
            payloads[1]["tournament_game"] = other.pk
        barrier = Barrier(2)

        def submit(payload):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = APIClient().post(
                    "/api/registrations/submit/",
                    payload,
                    format="json",
                    HTTP_X_REGISTRATION_ACCESS="ef" * 32,
                )
                return response.status_code, response.data
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, payloads))
        self.assertEqual(
            sorted(code for code, _ in results),
            [201, 409] if different_divisions else [200, 201],
            results,
        )
        self.assertEqual(RegistrationAccess.objects.count(), 1)
        self.assertEqual(Registration.objects.count(), 3)
        if not different_divisions:
            self.assertEqual(results[0][1]["id"], results[1][1]["id"])
            self.assertEqual(
                results[0][1]["payment_due_at"], results[1][1]["payment_due_at"]
            )

    def test_same_credential_race_creates_one_registration(self):
        self.race()

    def test_same_credential_across_divisions_conflicts_without_deadlock(self):
        self.race(different_divisions=True)
