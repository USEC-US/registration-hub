"""PostgreSQL races use real transactions and independent thread connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from registrations.models import PaymentAttempt, Registration
from registrations.reservations import active_registrations, expire_due_registrations
from registrations.services import (
    RegistrationMemberInput,
    submit_registration,
    submit_payment_attempt,
    review_payment_attempt,
)
from registrations.tests import test_api
from registrations.tests.images import payment_image


class ReservationConcurrencyTests(TransactionTestCase):
    setUp = test_api.RegistrationOwnershipApiTests.setUp
    _create_registration = test_api.RegistrationOwnershipApiTests._create_registration

    def race(self, *operations):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock races require PostgreSQL")
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                barrier.wait(timeout=10)
                try:
                    return operation()
                except ValidationError:
                    return "denied"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=20) for future in futures]

    def submit(self, tag):
        result = submit_registration(
            submitted_by=None,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            submitter_role="captain",
            contact_facebook_snapshot="fb/test",
            contact_phone_snapshot="0900000000",
            members=[
                RegistrationMemberInput(
                    gamer_tag_snapshot=tag,
                    first_name_snapshot="Test",
                    last_name_snapshot="Player",
                    date_of_birth_snapshot=date(2000, 1, 1),
                    institution_label="Test school",
                    is_captain=True,
                    display_order=1,
                )
            ],
        )
        return result.pk

    def empty_division(self, capacity):
        Registration.objects.all().delete()
        self.tournament_game.registration_capacity = capacity
        self.tournament_game.save()

    def test_last_slot_allows_one_committed_reservation(self):
        self.empty_division(1)
        results = self.race(lambda: self.submit("one"), lambda: self.submit("two"))
        self.assertEqual(results.count("denied"), 1)
        self.assertEqual(active_registrations(now=timezone.now()).count(), 1)
        self.assertEqual(Registration.objects.get().members.count(), 1)

    def test_duplicate_claim_allows_one_even_with_spare_capacity(self):
        self.empty_division(2)
        results = self.race(lambda: self.submit("same"), lambda: self.submit(" SAME "))
        self.assertEqual(results.count("denied"), 1)
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Registration.objects.get().members.count(), 1)

    def test_simultaneous_credential_free_submissions_both_receive_deadlines(self):
        self.empty_division(2)
        results = self.race(lambda: self.submit("one"), lambda: self.submit("two"))
        self.assertNotIn("denied", results)
        self.assertEqual(
            Registration.objects.filter(
                payment_due_at__isnull=False, payment_hold_minutes_snapshot=60
            ).count(),
            2,
        )

    def overdue(self, pending=False):
        self.registration.payment_due_at = timezone.now() - timedelta(seconds=1)
        self.registration.payment_hold_minutes_snapshot = 60
        self.registration.save()
        if pending:
            return PaymentAttempt.objects.create(
                registration=self.registration, amount=50000, currency="VND"
            )

    def test_proof_at_expiry_cannot_revive_released_reservation(self):
        self.overdue()
        results = self.race(
            lambda: submit_payment_attempt(
                actor=self.owner,
                registration_id=self.registration.pk,
                amount=self.registration.fee_amount_snapshot,
                currency="VND",
                proof_file=payment_image(),
            ),
            lambda: expire_due_registrations(division_id=self.tournament_game.pk),
        )
        self.assertIn("denied", results)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, "EXPIRED")
        self.assertFalse(self.registration.payment_attempts.exists())

    def test_pending_review_and_cleanup_preserve_replacement_window(self):
        attempt = self.overdue(pending=True)
        self.owner.is_superuser = True
        results = self.race(
            lambda: review_payment_attempt(
                actor=self.owner,
                payment_attempt_id=attempt.pk,
                status="REJECTED",
                note="Unreadable",
            ),
            lambda: expire_due_registrations(division_id=self.tournament_game.pk),
        )
        self.assertNotIn("denied", results)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, "SUBMITTED")
        self.assertGreater(
            self.registration.payment_due_at, timezone.now() + timedelta(minutes=59)
        )
        self.assertEqual(self.registration.payment_attempts.get().status, "REJECTED")

    def test_repeated_cleanup_appends_exactly_one_event(self):
        self.overdue()
        results = self.race(
            lambda: expire_due_registrations(), lambda: expire_due_registrations()
        )
        self.assertEqual(sorted(results), [0, 1])
        self.assertEqual(
            self.registration.status_events.filter(to_status="EXPIRED").count(), 1
        )

    def test_proof_before_deadline_protects_against_cleanup(self):
        self.overdue()
        self.registration.payment_due_at = timezone.now() + timedelta(minutes=1)
        self.registration.save()
        results = self.race(
            lambda: submit_payment_attempt(
                actor=self.owner,
                registration_id=self.registration.pk,
                amount=self.registration.fee_amount_snapshot,
                currency="VND",
                proof_file=payment_image(),
            ),
            lambda: expire_due_registrations(division_id=self.tournament_game.pk),
        )
        self.assertNotIn("denied", results)
        # Once accepted, staff delay beyond the original deadline cannot release it.
        Registration.objects.filter(pk=self.registration.pk).update(
            payment_due_at=timezone.now()
        )
        self.assertEqual(
            expire_due_registrations(division_id=self.tournament_game.pk), 0
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, "SUBMITTED")
        self.assertEqual(self.registration.payment_attempts.get().status, "PENDING")

    def test_payment_commit_failure_removes_file(self):
        from pathlib import Path
        from unittest.mock import patch
        from django.conf import settings
        from django.db import OperationalError

        with patch.object(
            connection, "commit", side_effect=OperationalError("commit failed")
        ):
            with self.assertRaises(OperationalError):
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
