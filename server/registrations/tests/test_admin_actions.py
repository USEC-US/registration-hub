from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.tests.factories import create_account
from registrations.admin import PaymentAttemptAdmin, RegistrationAdmin
from registrations.models import PaymentAttempt, Registration
from tournaments.models import Game, Tournament, TournamentGame


class GuardedAdminTests(TestCase):
    def setUp(self):
        self.actor = create_account(
            email="organizer@example.com",
            password="strong-password",
            first_name="Organizer",
            last_name="Staff",
            is_staff=True,
        )
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(name="Summer", slug="summer")
        tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(minutes=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="50000.00",
            fee_currency="VND",
        )
        self.registration = Registration.objects.create(
            tournament_game=tournament_game,
            submitted_by=self.actor,
            team_name="",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot="50000.00",
            fee_currency_snapshot="VND",
        )
        self.payment_attempt = PaymentAttempt.objects.create(
            registration=self.registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            amount="50000.00",
            currency="VND",
        )
        self.request = RequestFactory().post("/admin/")
        self.request.user = self.actor

    def test_registration_admin_blocks_direct_edits_and_delegates_transition(self):
        registration_admin = RegistrationAdmin(Registration, AdminSite())
        self.assertFalse(registration_admin.has_add_permission(self.request))
        self.assertFalse(
            registration_admin.has_delete_permission(self.request, self.registration)
        )
        self.assertIn(
            "submitted_by",
            registration_admin.get_readonly_fields(self.request, self.registration),
        )

        with (
            patch.object(registration_admin, "message_user"),
            patch("registrations.admin.start_review") as start_review_command,
        ):
            registration_admin.mark_under_review(
                self.request, Registration.objects.filter(pk=self.registration.pk)
            )

        start_review_command.assert_called_once_with(
            actor=self.actor, registration_id=self.registration.pk
        )

    def test_payment_admin_delegates_to_payment_service(self):
        payment_admin = PaymentAttemptAdmin(PaymentAttempt, AdminSite())

        with (
            patch.object(payment_admin, "message_user"),
            patch("registrations.admin.review_payment_attempt") as review_command,
        ):
            payment_admin.verify_selected(
                self.request,
                PaymentAttempt.objects.filter(pk=self.payment_attempt.pk),
            )

        review_command.assert_called_once_with(
            actor=self.actor,
            payment_attempt_id=self.payment_attempt.pk,
            status=PaymentAttempt.Status.VERIFIED,
        )

    def test_direct_model_permissions_do_not_bypass_organizer_membership(self):
        outsider = create_account(
            email="outside-staff@example.com",
            password="strong-password",
            first_name="Outside",
            last_name="Staff",
            is_staff=True,
        )
        outsider.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="registrations", codename="view_registration"
            ),
            Permission.objects.get(
                content_type__app_label="registrations", codename="change_registration"
            ),
            Permission.objects.get(
                content_type__app_label="registrations", codename="view_paymentattempt"
            ),
            Permission.objects.get(
                content_type__app_label="registrations",
                codename="change_paymentattempt",
            ),
        )
        outsider_request = RequestFactory().get("/admin/")
        outsider_request.user = outsider
        registration_admin = RegistrationAdmin(Registration, AdminSite())
        payment_admin = PaymentAttemptAdmin(PaymentAttempt, AdminSite())

        self.assertFalse(registration_admin.has_module_permission(outsider_request))
        self.assertFalse(
            registration_admin.has_view_permission(outsider_request, self.registration)
        )
        self.assertFalse(
            registration_admin.has_change_permission(
                outsider_request, self.registration
            )
        )
        self.assertFalse(payment_admin.has_module_permission(outsider_request))
        self.assertFalse(
            payment_admin.has_view_permission(outsider_request, self.payment_attempt)
        )
        self.assertFalse(
            payment_admin.has_change_permission(outsider_request, self.payment_attempt)
        )

    def test_reject_payment_requires_a_reason_form(self):
        payment_admin = PaymentAttemptAdmin(PaymentAttempt, AdminSite())
        response = payment_admin.reject_selected(
            self.request, PaymentAttempt.objects.filter(pk=self.payment_attempt.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("reason", response.context_data["form"].fields)
        self.payment_attempt.refresh_from_db()
        self.assertEqual(self.payment_attempt.status, "PENDING")

    def test_reject_payment_blank_reason_keeps_pending_then_reason_is_saved(self):
        payment_admin = PaymentAttemptAdmin(PaymentAttempt, AdminSite())
        self.actor.is_superuser = True
        for reason in (" ", "Account number is unreadable"):
            request = RequestFactory().post(
                "/admin/", {"confirm_rejection": "1", "reason": reason}
            )
            request.user = self.actor
            with patch.object(payment_admin, "message_user"):
                response = payment_admin.reject_selected(
                    request, PaymentAttempt.objects.filter(pk=self.payment_attempt.pk)
                )
            self.payment_attempt.refresh_from_db()
            if not reason.strip():
                self.assertIn("reason", response.context_data["form"].errors)
                self.assertEqual(self.payment_attempt.status, "PENDING")
            else:
                self.assertIsNone(response)
                self.assertEqual(self.payment_attempt.status, "REJECTED")
                self.assertEqual(self.payment_attempt.review_note, reason)
