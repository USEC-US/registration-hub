from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from registrations.models import PaymentAttempt, Registration
from registrations.tests import test_api
from registrations.services import (
    submit_payment_attempt,
    review_payment_attempt,
    approve_registration,
)
from registrations.tests.images import payment_image


class ReservationTests(TestCase):
    setUp = test_api.RegistrationOwnershipApiTests.setUp
    _create_registration = test_api.RegistrationOwnershipApiTests._create_registration

    def timed(self):
        self.registration.payment_due_at = timezone.now()
        self.registration.payment_hold_minutes_snapshot = 60
        self.registration.save()
        return self.registration

    def test_overdue_unpaid_entry_stops_holding_capacity_without_cron(self):
        from registrations.reservations import active_registrations

        registration = self.timed()
        self.assertFalse(
            active_registrations(now=registration.payment_due_at)
            .filter(pk=registration.pk)
            .exists()
        )
        self.assertTrue(Registration.objects.filter(pk=registration.pk).exists())

    def test_pending_and_verified_protect_without_count_multiplication(self):
        from registrations.reservations import active_registrations, payment_state

        registration = self.timed()
        for status in ("PENDING", "VERIFIED"):
            PaymentAttempt.objects.create(
                registration=registration, amount=50000, currency="VND", status=status
            )
        self.assertEqual(
            active_registrations(now=timezone.now()).filter(pk=registration.pk).count(),
            1,
        )
        self.assertEqual(payment_state(registration), "VERIFIED")

    def test_cleanup_is_idempotent_and_historical_entries_survive(self):
        from registrations.reservations import expire_due_registrations

        self.timed()
        self.assertEqual(
            expire_due_registrations(division_id=self.tournament_game.pk), 1
        )
        self.assertEqual(
            expire_due_registrations(division_id=self.tournament_game.pk), 0
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, "EXPIRED")
        self.assertEqual(
            self.registration.status_events.filter(to_status="EXPIRED").count(), 1
        )
        self.assertEqual(Registration.objects.filter(status="SUBMITTED").count(), 1)

    def test_overdue_upload_is_rejected(self):
        self.timed()
        with self.assertRaises(ValidationError):
            submit_payment_attempt(
                actor=self.owner,
                registration_id=self.registration.pk,
                amount=self.registration.fee_amount_snapshot,
                currency="VND",
                proof_file=payment_image(),
            )
        self.assertFalse(self.registration.payment_attempts.exists())

    def test_rejected_proof_requires_reason_and_resets_window(self):
        self.timed()
        self.owner.is_superuser = True
        attempt = PaymentAttempt.objects.create(
            registration=self.registration, amount=50000, currency="VND"
        )
        with self.assertRaises(ValidationError):
            review_payment_attempt(
                actor=self.owner, payment_attempt_id=attempt.pk, status="REJECTED"
            )
        before = timezone.now()
        review_payment_attempt(
            actor=self.owner,
            payment_attempt_id=attempt.pk,
            status="REJECTED",
            note="Unreadable",
        )
        self.registration.refresh_from_db()
        self.assertGreaterEqual(
            self.registration.payment_due_at, before + timedelta(minutes=60)
        )

    def test_timed_unpaid_approval_is_rejected(self):
        self.timed()
        self.registration.payment_due_at = timezone.now() + timedelta(minutes=30)
        self.registration.status = "UNDER_REVIEW"
        self.registration.save()
        self.owner.is_superuser = True
        with self.assertRaises(ValidationError):
            approve_registration(actor=self.owner, registration_id=self.registration.pk)

    def test_public_serializer_fallback_and_annotated_counts_release_expiry(self):
        from tournaments.serializers import PublicTournamentGameSerializer
        from tournaments.views import PublicTournamentViewSet

        self.timed()
        self.tournament_game.registration_capacity = 2
        self.tournament_game.save()
        self.assertEqual(
            PublicTournamentGameSerializer(self.tournament_game).data[
                "capacity_remaining"
            ],
            1,
        )
        tournament = (
            PublicTournamentViewSet()
            .get_queryset()
            .get(pk=self.tournament_game.tournament_id)
        )
        division = tournament.tournament_games.all()[0]
        self.assertEqual(
            PublicTournamentGameSerializer(division).data["capacity_remaining"], 1
        )

    def test_receipt_exposes_effective_expiry_and_payment_state(self):
        from registrations.serializers import RegistrationReadSerializer

        self.timed()
        data = RegistrationReadSerializer(self.registration).data
        self.assertTrue(data["expired"])
        self.assertEqual(data["payment_state"], "UNPAID")
        self.assertIsNotNone(data["payment_due_at"])

    def test_pending_duplicate_and_verified_uploads_are_rejected(self):
        self.timed()
        for status in ("PENDING", "VERIFIED"):
            self.registration.payment_attempts.all().delete()
            PaymentAttempt.objects.create(
                registration=self.registration,
                amount=50000,
                currency="VND",
                status=status,
            )
            with self.assertRaises(ValidationError):
                submit_payment_attempt(
                    actor=self.owner,
                    registration_id=self.registration.pk,
                    amount=self.registration.fee_amount_snapshot,
                    currency="VND",
                    proof_file=payment_image(),
                )
            self.assertEqual(self.registration.payment_attempts.count(), 1)

    def test_deadline_is_checked_after_sanitization(self):
        from unittest.mock import patch
        from registrations.images import prepare_payment_image

        self.timed()
        now = timezone.now()
        self.registration.payment_due_at = now + timedelta(minutes=1)
        self.registration.save()

        def prepare(file):
            prepared = prepare_payment_image(file)
            Registration.objects.filter(pk=self.registration.pk).update(
                payment_due_at=now
            )
            return prepared

        with patch("registrations.services.prepare_payment_image", side_effect=prepare):
            with self.assertRaises(ValidationError):
                submit_payment_attempt(
                    actor=self.owner,
                    registration_id=self.registration.pk,
                    amount=self.registration.fee_amount_snapshot,
                    currency="VND",
                    proof_file=payment_image(),
                )
        self.assertFalse(self.registration.payment_attempts.exists())

    def test_boolean_access_cannot_authorize_guest(self):
        from django.core.exceptions import PermissionDenied

        self.registration.submitted_by = None
        self.registration.save()
        with self.assertRaises(PermissionDenied):
            submit_payment_attempt(
                actor=None,
                registration_access=True,
                registration_id=self.registration.pk,
                amount=self.registration.fee_amount_snapshot,
                currency="VND",
                proof_file=payment_image(),
            )

    def test_failed_payment_save_removes_sanitized_file(self):
        from pathlib import Path
        from unittest.mock import patch
        from django.conf import settings
        from django.db import IntegrityError

        original = PaymentAttempt.save

        def fail_after_file_save(attempt, *args, **kwargs):
            original(attempt, *args, **kwargs)
            raise IntegrityError("persistence failed")

        with patch.object(PaymentAttempt, "save", fail_after_file_save):
            with self.assertRaises(IntegrityError):
                submit_payment_attempt(
                    actor=self.owner,
                    registration_id=self.registration.pk,
                    amount=self.registration.fee_amount_snapshot,
                    currency="VND",
                    proof_file=payment_image(),
                )
        self.assertFalse(self.registration.payment_attempts.exists())
        self.assertFalse(
            [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]
        )

    def test_expiry_command_is_scoped_and_repeatable(self):
        from io import StringIO
        from django.core.management import call_command

        self.timed()
        output = StringIO()
        call_command(
            "expire_unpaid_registrations",
            division=self.tournament_game.pk + 9999,
            stdout=output,
        )
        self.assertIn("Expired 0", output.getvalue())
        output = StringIO()
        call_command(
            "expire_unpaid_registrations",
            division=self.tournament_game.pk,
            stdout=output,
        )
        call_command(
            "expire_unpaid_registrations",
            division=self.tournament_game.pk,
            stdout=output,
        )
        self.assertEqual(
            output.getvalue(),
            "Expired 1 registration(s).\nExpired 0 registration(s).\n",
        )

    def test_rejection_with_another_pending_proof_does_not_reset_hold(self):
        self.timed()
        self.owner.is_superuser = True
        first = PaymentAttempt.objects.create(
            registration=self.registration, amount=50000, currency="VND"
        )
        PaymentAttempt.objects.create(
            registration=self.registration, amount=50000, currency="VND"
        )
        due = self.registration.payment_due_at
        review_payment_attempt(
            actor=self.owner,
            payment_attempt_id=first.pk,
            status="REJECTED",
            note="Unreadable",
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.payment_due_at, due)

    def test_public_payment_reference_releases_effective_capacity(self):
        from registrations.payments import reserve_payment_reference

        self.timed()
        self.tournament_game.registration_capacity = 2
        self.tournament_game.save()
        intent = reserve_payment_reference(tournament_game_id=self.tournament_game.pk)
        self.assertIsNotNone(intent.pk)


class ReceiptQueryTests(TestCase):
    setUp = test_api.RegistrationOwnershipApiTests.setUp
    _create_registration = test_api.RegistrationOwnershipApiTests._create_registration

    def test_multi_entry_account_receipts_use_one_payment_prefetch(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from rest_framework.test import APIClient

        for status in ("PENDING", "VERIFIED", "REJECTED"):
            entry = self._create_registration(self.owner)
            entry.payment_due_at = timezone.now() - timedelta(minutes=1)
            entry.save()
            PaymentAttempt.objects.create(
                registration=entry, amount=50000, currency="VND", status=status
            )
        self.registration.payment_due_at = timezone.now() - timedelta(minutes=1)
        self.registration.save()
        client = APIClient()
        client.force_authenticate(user=self.owner)
        with CaptureQueriesContext(connection) as captured:
            response = client.get("/api/registrations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 4)
        self.assertEqual(
            {item["payment_state"] for item in response.data},
            {"UNPAID", "PENDING", "VERIFIED", "REJECTED"},
        )
        self.assertEqual(sum(item["expired"] for item in response.data), 2)
        payment_queries = [
            query["sql"]
            for query in captured
            if 'FROM "registrations_paymentattempt"' in query["sql"]
        ]
        self.assertEqual(len(payment_queries), 1, payment_queries)
        self.assertLessEqual(len(captured), 4)

    def test_service_state_is_fresh_after_upload_reject_and_replacement(self):
        from registrations.reservations import payment_state

        self.registration.payment_due_at = timezone.now() + timedelta(minutes=10)
        self.registration.payment_hold_minutes_snapshot = 60
        self.registration.save()
        # A read-prefetched instance must not leak stale state into service locks.
        cached = Registration.objects.prefetch_related("payment_attempts").get(
            pk=self.registration.pk
        )
        self.assertEqual(payment_state(cached), "UNPAID")
        attempt = submit_payment_attempt(
            actor=self.owner,
            registration_id=cached.pk,
            amount=cached.fee_amount_snapshot,
            currency="VND",
            proof_file=payment_image(),
        )
        self.assertEqual(payment_state(attempt.registration), "PENDING")
        self.owner.is_superuser = True
        reviewed = review_payment_attempt(
            actor=self.owner,
            payment_attempt_id=attempt.pk,
            status="REJECTED",
            note="Unreadable",
        )
        self.assertEqual(payment_state(reviewed.registration), "REJECTED")
        self.assertGreater(
            reviewed.registration.payment_due_at, timezone.now() + timedelta(minutes=59)
        )
        replacement = submit_payment_attempt(
            actor=self.owner,
            registration_id=cached.pk,
            amount=cached.fee_amount_snapshot,
            currency="VND",
            proof_file=payment_image(),
        )
        self.assertEqual(payment_state(replacement.registration), "PENDING")
        verified = review_payment_attempt(
            actor=self.owner, payment_attempt_id=replacement.pk, status="VERIFIED"
        )
        self.assertEqual(payment_state(verified.registration), "VERIFIED")
        cached.refresh_from_db()
        self.assertEqual(payment_state(cached), "VERIFIED")
