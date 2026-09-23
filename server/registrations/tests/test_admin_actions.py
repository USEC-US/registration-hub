from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group, Permission
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
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


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class RegistrationDecisionUiTests(TestCase):
    def setUp(self):
        self.actor = create_account(
            email="reviewer@example.com",
            password="strong-password",
            first_name="Review",
            last_name="Staff",
            is_staff=True,
        )
        group = Group.objects.create(name="Organizers")
        group.permissions.add(
            *Permission.objects.filter(
                content_type__app_label="registrations",
                codename__in=("view_registration", "change_registration"),
            )
        )
        self.actor.groups.add(group)
        division = TournamentGame.objects.create(
            tournament=Tournament.objects.create(name="Autumn", slug="autumn"),
            game=Game.objects.create(name="Valorant", slug="valorant"),
            main_roster_size=1,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount=0,
        )
        self.registration = Registration.objects.create(
            tournament_game=division,
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        self.client.force_login(self.actor)

    def url(self, name):
        return reverse(
            f"admin:registrations_registration_{name}", args=[self.registration.pk]
        )

    def test_decisions_are_visible_on_table_and_detail_and_require_post(self):
        list_url = reverse("admin:registrations_registration_changelist")
        detail_url = self.url("change")
        start_url = self.url("start_review_detail")
        approve_url = self.url("approve_detail")
        reject_url = self.url("reject_detail")

        for page in (list_url, detail_url):
            self.assertContains(self.client.get(page), start_url)
            self.assertNotContains(self.client.get(page), approve_url)
        self.assertContains(self.client.get(start_url), "Start review")
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.SUBMITTED)
        self.assertEqual(self.client.post(start_url).status_code, 302)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.UNDER_REVIEW)

        for page in (list_url, detail_url):
            self.assertContains(self.client.get(page), approve_url)
            self.assertContains(self.client.get(page), reject_url)
            self.assertNotContains(self.client.get(page), start_url)
        self.assertContains(self.client.get(reject_url), "Rejection reason")
        self.assertContains(
            self.client.post(reject_url, {"reason": " "}), "Rejection reason"
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.UNDER_REVIEW)
        self.assertEqual(self.client.post(approve_url).status_code, 302)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.APPROVED)
        self.assertEqual(self.registration.status_events.count(), 2)
        for page in (list_url, detail_url):
            self.assertNotContains(self.client.get(page), approve_url)
            self.assertNotContains(self.client.get(page), reject_url)
        self.assertContains(
            self.client.post(reject_url, {"reason": "Too late"}),
            "Cannot move a APPROVED registration",
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.APPROVED)

    def test_rejection_records_reason_and_view_only_staff_cannot_decide(self):
        self.registration.status = Registration.Status.UNDER_REVIEW
        self.registration.save(update_fields=("status",))
        reject_url = self.url("reject_detail")
        self.assertEqual(
            self.client.post(reject_url, {"reason": "Missing student ID"}).status_code,
            302,
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.REJECTED)
        self.assertEqual(
            self.registration.status_events.last().note, "Missing student ID"
        )

        group = self.actor.groups.get()
        group.permissions.remove(Permission.objects.get(codename="change_registration"))
        self.actor = type(self.actor).objects.get(pk=self.actor.pk)
        self.client.force_login(self.actor)
        self.registration.status = Registration.Status.UNDER_REVIEW
        self.registration.save(update_fields=("status",))
        for page in (
            reverse("admin:registrations_registration_changelist"),
            self.url("change"),
        ):
            self.assertNotContains(self.client.get(page), self.url("approve_detail"))
        self.assertEqual(self.client.post(self.url("approve_detail")).status_code, 403)

    def test_decision_post_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.actor)
        self.assertEqual(
            csrf_client.post(self.url("start_review_detail")).status_code, 403
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.SUBMITTED)
        self.assertEqual(
            csrf_client.get(self.url("start_review_detail")).status_code, 200
        )
        token = csrf_client.cookies["csrftoken"].value
        self.assertEqual(
            csrf_client.post(
                self.url("start_review_detail"), HTTP_X_CSRFTOKEN=token
            ).status_code,
            302,
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.UNDER_REVIEW)
