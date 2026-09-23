from datetime import date
from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.tests.factories import create_account
from registrations.models import PaymentAttempt, Registration
from registrations.services import (
    RegistrationMemberInput,
    approve_registration,
    reject_registration,
    review_payment_attempt,
    start_review,
    submit_payment_attempt,
    submit_registration,
)
from tournaments.models import Game, Tournament, TournamentGame

from .images import payment_image


class RegistrationServiceTests(TestCase):
    def setUp(self):
        from .payment_settings import configure_test_payments

        configure_test_payments()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.captain = create_account(
            email="captain@example.com",
            password="strong-password",
            first_name="Captain",
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
            registration_capacity=1,
            fee_amount="50000.00",
            fee_currency="VND",
        )

    def _member(self, *, gamer_tag="captain", is_captain=True, display_order=1):
        return RegistrationMemberInput(
            first_name_snapshot="Player",
            last_name_snapshot="Example",
            date_of_birth_snapshot=date(2005, 1, 1),
            student_id_snapshot="0012345",
            gamer_tag_snapshot=gamer_tag,
            school_snapshot="HCMUS",
            is_captain=is_captain,
            display_order=display_order,
        )

    def _submit_solo(self, *, submitted_by=None):
        return submit_registration(
            submitter_role="captain",
            contact_facebook_snapshot="https://facebook.com/example",
            contact_phone_snapshot="0900000000",
            submitted_by=submitted_by or self.captain,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            members=[self._member()],
        )

    def _organizer(self):
        organizer = create_account(
            email="organizer@example.com",
            password="strong-password",
            first_name="Organizer",
            last_name="Staff",
            is_staff=True,
        )
        group, _ = Group.objects.get_or_create(name="Organizers")
        organizer.groups.add(group)
        organizer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="registrations", codename="change_registration"
            ),
            Permission.objects.get(
                content_type__app_label="registrations",
                codename="change_paymentattempt",
            ),
        )
        return organizer

    def test_submission_snapshots_trimmed_values_and_creates_event(self):
        registration = submit_registration(
            submitter_role="captain",
            contact_facebook_snapshot="https://facebook.com/example",
            contact_phone_snapshot="0900000000",
            submitted_by=self.captain,
            tournament_game_id=self.tournament_game.pk,
            team_name="  ",
            members=[
                RegistrationMemberInput(
                    first_name_snapshot="Player",
                    last_name_snapshot="Example",
                    date_of_birth_snapshot=date(2005, 1, 1),
                    student_id_snapshot="0012345",
                    gamer_tag_snapshot="  captain  ",
                    school_snapshot=" HCMUS ",
                    is_captain=True,
                    display_order=1,
                )
            ],
        )

        member = registration.members.get()
        event = registration.status_events.get()
        self.assertEqual(registration.team_name, "")
        self.assertEqual(member.gamer_tag_snapshot, "captain")
        self.assertEqual(member.school_snapshot, "HCMUS")
        self.assertEqual(member.user_id, self.captain.pk)
        self.assertEqual(registration.fee_amount_snapshot, Decimal("50000.00"))
        self.assertEqual(event.from_status, "")
        self.assertEqual(event.to_status, Registration.Status.SUBMITTED)
        self.assertEqual(event.actor, self.captain)

    def test_capacity_blocks_a_second_active_entry(self):
        self._submit_solo()

        with self.assertRaises(ValidationError):
            self._submit_solo(submitted_by=self.other_user)

    def test_closed_registration_window_is_rejected(self):
        self.tournament_game.registration_closes_at = timezone.now() - timedelta(
            seconds=1
        )
        self.tournament_game.save(update_fields=("registration_closes_at",))

        with self.assertRaises(ValidationError):
            self._submit_solo()

    def test_unpublished_tournament_is_rejected(self):
        tournament = self.tournament_game.tournament
        tournament.is_published = False
        tournament.save(update_fields=("is_published",))

        with self.assertRaisesMessage(ValidationError, "Tournament is not published."):
            self._submit_solo()

    def test_roster_requires_exactly_one_captain_and_contiguous_display_order(self):
        self.tournament_game.main_roster_size = 2
        self.tournament_game.substitute_limit = 0
        self.tournament_game.registration_capacity = None
        self.tournament_game.save(
            update_fields=(
                "main_roster_size",
                "substitute_limit",
                "registration_capacity",
            )
        )

        with self.assertRaises(ValidationError):
            submit_registration(
                submitter_role="captain",
                contact_facebook_snapshot="https://facebook.com/example",
                contact_phone_snapshot="0900000000",
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="team",
                members=[
                    self._member(is_captain=False),
                    self._member(is_captain=False),
                ],
            )

        with self.assertRaises(ValidationError):
            submit_registration(
                submitter_role="captain",
                contact_facebook_snapshot="https://facebook.com/example",
                contact_phone_snapshot="0900000000",
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="team",
                members=[
                    self._member(display_order=0),
                    self._member(
                        gamer_tag="teammate", is_captain=False, display_order=2
                    ),
                ],
            )

        with self.assertRaises(ValidationError):
            submit_registration(
                submitter_role="captain",
                contact_facebook_snapshot="https://facebook.com/example",
                contact_phone_snapshot="0900000000",
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="team",
                members=[
                    self._member(display_order=1),
                    self._member(
                        gamer_tag="teammate", is_captain=False, display_order=1
                    ),
                ],
            )

        with self.assertRaises(ValidationError):
            submit_registration(
                submitter_role="captain",
                contact_facebook_snapshot="https://facebook.com/example",
                contact_phone_snapshot="0900000000",
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="team",
                members=[
                    self._member(display_order=2),
                    self._member(
                        gamer_tag="teammate", is_captain=False, display_order=3
                    ),
                ],
            )

    def test_team_name_is_required_only_for_team_games(self):
        with self.assertRaises(ValidationError):
            submit_registration(
                submitter_role="captain",
                contact_facebook_snapshot="https://facebook.com/example",
                contact_phone_snapshot="0900000000",
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="not-for-solo",
                members=[self._member()],
            )

        self.tournament_game.main_roster_size = 2
        self.tournament_game.substitute_limit = 0
        self.tournament_game.registration_capacity = None
        self.tournament_game.save(
            update_fields=(
                "main_roster_size",
                "substitute_limit",
                "registration_capacity",
            )
        )
        with self.assertRaises(ValidationError):
            submit_registration(
                submitter_role="captain",
                contact_facebook_snapshot="https://facebook.com/example",
                contact_phone_snapshot="0900000000",
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="",
                members=[
                    self._member(),
                    self._member(gamer_tag="teammate", display_order=2),
                ],
            )

    def test_only_authorized_organizer_can_transition_registration(self):
        registration = self._submit_solo()
        unauthorized = create_account(
            email="staff@example.com",
            password="strong-password",
            first_name="Unauthorized",
            last_name="Staff",
            is_staff=True,
        )

        with self.assertRaises(PermissionDenied):
            start_review(actor=unauthorized, registration_id=registration.pk)

        organizer = self._organizer()
        registration = start_review(actor=organizer, registration_id=registration.pk)
        PaymentAttempt.objects.create(
            registration=registration, amount=50000, currency="VND", status="VERIFIED"
        )
        registration = approve_registration(
            actor=organizer, registration_id=registration.pk
        )

        self.assertEqual(registration.status, Registration.Status.APPROVED)
        self.assertEqual(registration.status_events.count(), 3)

    def test_approval_verifies_submitted_payment_proof(self):
        from registrations.reservations import expire_due_registrations, payment_state

        organizer = self._organizer()
        registration = start_review(
            actor=organizer, registration_id=self._submit_solo().pk
        )
        attempt = PaymentAttempt.objects.create(
            registration=registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            amount=registration.fee_amount_snapshot,
            currency=registration.fee_currency_snapshot,
            proof_file=payment_image(),
        )

        approve_registration(actor=organizer, registration_id=registration.pk)

        registration.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.APPROVED)
        self.assertEqual(attempt.status, PaymentAttempt.Status.VERIFIED)
        self.assertEqual(attempt.reviewed_by_id, organizer.pk)
        self.assertIsNotNone(attempt.reviewed_at)
        self.assertEqual(payment_state(registration), "VERIFIED")
        registration.payment_due_at = timezone.now() - timedelta(minutes=1)
        registration.save(update_fields=("payment_due_at",))
        self.assertEqual(
            expire_due_registrations(division_id=registration.tournament_game_id), 0
        )
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.APPROVED)

    def test_rejection_requires_reason_and_only_from_under_review(self):
        registration = self._submit_solo()
        organizer = self._organizer()

        with self.assertRaises(ValidationError):
            reject_registration(
                actor=organizer, registration_id=registration.pk, note=" "
            )

        with self.assertRaises(ValidationError):
            reject_registration(
                actor=organizer, registration_id=registration.pk, note="No"
            )

        start_review(actor=organizer, registration_id=registration.pk)
        rejected = reject_registration(
            actor=organizer, registration_id=registration.pk, note=" Missing document "
        )

        self.assertEqual(rejected.status, Registration.Status.REJECTED)
        self.assertEqual(rejected.status_events.last().note, "Missing document")

    def test_only_submitter_can_create_a_payment_attempt_with_valid_evidence(self):
        registration = self._submit_solo()

        with self.assertRaises(PermissionDenied):
            submit_payment_attempt(
                actor=self.other_user,
                registration_id=registration.pk,
                amount=Decimal("50000.00"),
                currency="VND",
                reference="BANK-1",
            )

        with self.assertRaises(ValidationError):
            submit_payment_attempt(
                actor=self.captain,
                registration_id=registration.pk,
                amount=Decimal("50000.00"),
                currency="VND",
            )

        attempt = submit_payment_attempt(
            actor=self.captain,
            registration_id=registration.pk,
            amount=Decimal("50000.00"),
            currency="vnd",
            proof_file=payment_image(),
        )

        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(attempt.currency, "VND")
        self.assertEqual(attempt.registration.status, Registration.Status.SUBMITTED)

    def test_payment_attempt_rejects_an_unpublished_tournament(self):
        registration = self._submit_solo()
        tournament = registration.tournament_game.tournament
        tournament.is_published = False
        tournament.save(update_fields=("is_published",))

        with self.assertRaisesMessage(ValidationError, "Tournament is not published."):
            submit_payment_attempt(
                actor=self.captain,
                registration_id=registration.pk,
                amount=Decimal("50000.00"),
                currency="VND",
                reference="BANK-1",
            )

        self.assertFalse(PaymentAttempt.objects.exists())

    def test_payment_attempt_rejects_fee_mismatches_and_no_fee_registration(self):
        registration = self._submit_solo()

        with self.assertRaises(ValidationError):
            submit_payment_attempt(
                actor=self.captain,
                registration_id=registration.pk,
                amount=Decimal("1.00"),
                currency="VND",
                reference="BANK-1",
            )

        with self.assertRaises(ValidationError):
            submit_payment_attempt(
                actor=self.captain,
                registration_id=registration.pk,
                amount=Decimal("50000.00"),
                currency="USD",
                reference="BANK-1",
            )

        registration.fee_amount_snapshot = Decimal("0.00")
        registration.save(update_fields=("fee_amount_snapshot",))
        with self.assertRaises(ValidationError):
            submit_payment_attempt(
                actor=self.captain,
                registration_id=registration.pk,
                amount=Decimal("0.00"),
                currency="VND",
                reference="BANK-1",
            )

    def test_organizer_reviews_pending_payment_without_changing_registration(self):
        registration = self._submit_solo()
        payment_attempt = submit_payment_attempt(
            actor=self.captain,
            registration_id=registration.pk,
            amount=Decimal("50000.00"),
            currency="VND",
            reference="BANK-1",
            proof_file=payment_image(),
        )
        organizer = self._organizer()

        with self.assertRaises(ValidationError):
            review_payment_attempt(
                actor=organizer,
                payment_attempt_id=payment_attempt.pk,
                status=PaymentAttempt.Status.PENDING,
            )

        reviewed = review_payment_attempt(
            actor=organizer,
            payment_attempt_id=payment_attempt.pk,
            status=PaymentAttempt.Status.VERIFIED,
            note=" confirmed ",
        )

        self.assertEqual(reviewed.status, PaymentAttempt.Status.VERIFIED)
        self.assertEqual(reviewed.reviewed_by, organizer)
        self.assertIsNotNone(reviewed.reviewed_at)
        self.assertEqual(reviewed.review_note, "confirmed")
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.SUBMITTED)

        with self.assertRaises(ValidationError):
            review_payment_attempt(
                actor=organizer,
                payment_attempt_id=payment_attempt.pk,
                status=PaymentAttempt.Status.REJECTED,
            )

    def test_credential_free_paid_submission_snapshots_duration_and_close_cap(self):
        from .payment_settings import configure_test_payments

        settings = configure_test_payments()
        settings.payment_hold_minutes = 120
        settings.save()
        closing = timezone.now() + timedelta(minutes=20)
        self.tournament_game.registration_closes_at = closing
        self.tournament_game.save()
        registration = self._submit_solo()
        self.assertEqual(registration.payment_due_at, closing)
        self.assertEqual(registration.payment_hold_minutes_snapshot, 120)
        self.assertEqual(
            registration.payment_intent.account_number_snapshot, settings.account_number
        )
        settings.payment_hold_minutes = 15
        settings.save()
        registration.refresh_from_db()
        self.assertEqual(registration.payment_due_at, closing)

    def test_missing_settings_reject_paid_but_not_free_submission(self):
        from registrations.models import PaymentSettings

        PaymentSettings.objects.all().delete()
        with self.assertRaises(ValidationError):
            self._submit_solo()
        self.assertFalse(Registration.objects.exists())
        self.tournament_game.fee_amount = 0
        self.tournament_game.save()
        registration = self._submit_solo()
        self.assertIsNone(registration.payment_due_at)
        self.assertIsNone(registration.payment_hold_minutes_snapshot)

    def test_expiry_releases_capacity_and_normalized_player_claim_together(self):
        registration = self._submit_solo()
        registration.payment_due_at = timezone.now()
        registration.save()
        replacement = self._submit_solo()
        registration.refresh_from_db()
        self.assertEqual(registration.status, "EXPIRED")
        self.assertNotEqual(replacement.pk, registration.pk)
        self.assertEqual(
            replacement.members.get().gamer_tag_snapshot,
            registration.members.get().gamer_tag_snapshot,
        )

    def test_initial_proof_sanitization_cannot_cross_registration_close(self):
        from unittest.mock import patch
        from registrations.images import prepare_payment_image

        closing = timezone.now() + timedelta(minutes=1)
        self.tournament_game.registration_closes_at = closing
        self.tournament_game.save()

        def prepare(file):
            prepared = prepare_payment_image(file)
            # The next authoritative read observes closing; no upload can extend it.
            time_patch.start()
            return prepared

        time_patch = patch("registrations.services.timezone.now", return_value=closing)
        self.addCleanup(time_patch.stop)
        with patch("registrations.services.prepare_payment_image", side_effect=prepare):
            with self.assertRaises(ValidationError):
                submit_registration(
                    submitted_by=self.captain,
                    tournament_game_id=self.tournament_game.pk,
                    team_name="",
                    members=[self._member()],
                    submitter_role="captain",
                    contact_facebook_snapshot="fb/me",
                    contact_phone_snapshot="0900000000",
                    proof_file=payment_image(),
                )
        self.assertFalse(Registration.objects.exists())

    def test_initial_proof_cannot_cross_deadline_during_intent_persistence(self):
        from unittest.mock import patch
        from registrations.models import PaymentIntent

        closing = timezone.now() + timedelta(minutes=1)
        self.tournament_game.registration_closes_at = closing
        self.tournament_game.save()
        original = PaymentIntent.save
        time_patch = patch("registrations.services.timezone.now", return_value=closing)
        self.addCleanup(time_patch.stop)

        def save(intent, *args, **kwargs):
            result = original(intent, *args, **kwargs)
            time_patch.start()
            return result

        with patch.object(PaymentIntent, "save", save):
            with self.assertRaises(ValidationError):
                submit_registration(
                    submitted_by=self.captain,
                    tournament_game_id=self.tournament_game.pk,
                    team_name="",
                    members=[self._member()],
                    submitter_role="captain",
                    contact_facebook_snapshot="fb/me",
                    contact_phone_snapshot="0900000000",
                    proof_file=payment_image(),
                )
        self.assertFalse(Registration.objects.exists())
