from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

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


class RegistrationServiceTests(TestCase):
    def setUp(self):
        self.captain = get_user_model().objects.create_user(
            email="captain@example.com", password="strong-password"
        )
        self.other_user = get_user_model().objects.create_user(
            email="other@example.com", password="strong-password"
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
            registration_capacity=1,
            fee_amount="50000.00",
            fee_currency="VND",
        )

    def _member(self, *, gamer_tag="captain", is_captain=True, display_order=1):
        return RegistrationMemberInput(
            gamer_tag_snapshot=gamer_tag,
            school_snapshot="HCMUS",
            is_captain=is_captain,
            display_order=display_order,
        )

    def _submit_solo(self, *, submitted_by=None):
        return submit_registration(
            submitted_by=submitted_by or self.captain,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            members=[self._member()],
        )

    def _organizer(self):
        organizer = get_user_model().objects.create_user(
            email="organizer@example.com",
            password="strong-password",
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
            submitted_by=self.captain,
            tournament_game_id=self.tournament_game.pk,
            team_name="  ",
            members=[
                RegistrationMemberInput(
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
        self.assertIsNone(member.user_id)
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
        self.tournament_game.team_size_min = 2
        self.tournament_game.team_size_max = 2
        self.tournament_game.registration_capacity = None
        self.tournament_game.save(
            update_fields=("team_size_min", "team_size_max", "registration_capacity")
        )

        with self.assertRaises(ValidationError):
            submit_registration(
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
                submitted_by=self.captain,
                tournament_game_id=self.tournament_game.pk,
                team_name="not-for-solo",
                members=[self._member()],
            )

        self.tournament_game.team_size_min = 2
        self.tournament_game.team_size_max = 2
        self.tournament_game.registration_capacity = None
        self.tournament_game.save(
            update_fields=("team_size_min", "team_size_max", "registration_capacity")
        )
        with self.assertRaises(ValidationError):
            submit_registration(
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
        unauthorized = get_user_model().objects.create_user(
            email="staff@example.com", password="strong-password", is_staff=True
        )

        with self.assertRaises(PermissionDenied):
            start_review(actor=unauthorized, registration_id=registration.pk)

        organizer = self._organizer()
        registration = start_review(actor=organizer, registration_id=registration.pk)
        registration = approve_registration(
            actor=organizer, registration_id=registration.pk
        )

        self.assertEqual(registration.status, Registration.Status.APPROVED)
        self.assertEqual(registration.status_events.count(), 3)

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
            proof_file=SimpleUploadedFile("proof.txt", b"payment proof"),
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
