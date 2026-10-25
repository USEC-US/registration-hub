from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tests.factories import create_account
from registrations.admin import PaymentAttemptAdmin, RegistrationAdmin
from registrations.models import (
    PaymentAttempt,
    PaymentIntent,
    Registration,
    RegistrationMember,
    RegistrationStatusEvent,
)
from registrations.tests.images import payment_image
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

    def test_payment_admin_has_no_standalone_review_actions(self):
        self.actor.is_superuser = True
        self.actor.save(update_fields=("is_superuser",))
        payment_admin = PaymentAttemptAdmin(PaymentAttempt, AdminSite())
        self.assertFalse(payment_admin.get_actions(self.request))

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
        self.assertContains(self.client.get(approve_url), "Approve registration")
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
        history_count = LogEntry.objects.filter(
            content_type__model="registration", object_id=str(self.registration.pk)
        ).count()
        for page in (list_url, detail_url):
            self.assertNotContains(self.client.get(page), approve_url)
            self.assertNotContains(self.client.get(page), reject_url)
        self.assertContains(
            self.client.post(reject_url, {"reason": "Too late"}),
            "Cannot move a APPROVED registration",
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.APPROVED)
        self.assertEqual(
            LogEntry.objects.filter(
                content_type__model="registration", object_id=str(self.registration.pk)
            ).count(),
            history_count,
        )

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
        self.assertContains(self.client.get(self.url("history")), "Missing student ID")
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

    def test_paid_approval_requires_payment_permission_and_names_both_decisions(self):
        self.registration.status = Registration.Status.UNDER_REVIEW
        self.registration.fee_amount_snapshot = 50000
        self.registration.save(update_fields=("status", "fee_amount_snapshot"))
        attempt = PaymentAttempt.objects.create(
            registration=self.registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            amount=50000,
            currency="VND",
            proof_file=payment_image(),
        )
        list_url = reverse("admin:registrations_registration_changelist")
        approve_url = self.url("approve_detail")
        self.assertNotContains(self.client.get(list_url), approve_url)
        self.assertEqual(self.client.get(approve_url).status_code, 403)
        self.actor.groups.get().permissions.add(
            Permission.objects.get(codename="view_paymentattempt"),
            Permission.objects.get(codename="change_paymentattempt"),
        )
        self.actor = type(self.actor).objects.get(pk=self.actor.pk)
        self.client.force_login(self.actor)
        self.assertContains(self.client.get(list_url), "Verify payment and approve")
        self.assertContains(self.client.get(approve_url), "Verify payment and approve")
        self.assertEqual(self.client.post(approve_url).status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.VERIFIED)
        self.assertContains(self.client.get(self.url("history")), "UNDER_REVIEW")

    def test_bulk_approval_explains_payment_effect_and_rejection_requires_reason(self):
        self.actor.is_superuser = True
        self.actor.save(update_fields=("is_superuser",))
        self.registration.status = Registration.Status.UNDER_REVIEW
        self.registration.save(update_fields=("status",))
        paid = Registration.objects.create(
            tournament_game=self.registration.tournament_game,
            status=Registration.Status.UNDER_REVIEW,
            fee_amount_snapshot=50000,
            fee_currency_snapshot="VND",
        )
        attempt = PaymentAttempt.objects.create(
            registration=paid,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            amount=50000,
            currency="VND",
            proof_file=payment_image(),
        )
        admin_obj = RegistrationAdmin(Registration, AdminSite())
        queryset = Registration.objects.filter(pk__in=(self.registration.pk, paid.pk))
        request = RequestFactory().post("/admin/")
        request.user = self.actor
        with patch.object(admin_obj, "message_user"):
            confirmation = admin_obj.approve_selected(request, queryset)
        confirmation.render()
        self.assertContains(confirmation, "Verify payment and approve")
        self.assertContains(confirmation, "Approve registration")
        request = RequestFactory().post("/admin/", {"confirm_action": "1"})
        request.user = self.actor
        with patch.object(admin_obj, "message_user"):
            admin_obj.approve_selected(request, queryset)
        self.registration.refresh_from_db()
        paid.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.APPROVED)
        self.assertEqual(paid.status, Registration.Status.APPROVED)
        self.assertEqual(attempt.status, PaymentAttempt.Status.VERIFIED)
        self.assertEqual(
            LogEntry.objects.filter(
                content_type__model="registration", object_id=str(paid.pk)
            ).count(),
            1,
        )

        rejected = Registration.objects.create(
            tournament_game=self.registration.tournament_game,
            status=Registration.Status.UNDER_REVIEW,
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        reject_query = Registration.objects.filter(pk=rejected.pk)
        request = RequestFactory().post(
            "/admin/", {"confirm_action": "1", "reason": " "}
        )
        request.user = self.actor
        invalid = admin_obj.reject_selected(request, reject_query)
        invalid.render()
        self.assertContains(invalid, "Rejection reason")
        self.assertNotContains(invalid, "verify payment and approve together")
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, Registration.Status.UNDER_REVIEW)
        request = RequestFactory().post(
            "/admin/", {"confirm_action": "1", "reason": "Missing student ID"}
        )
        request.user = self.actor
        with patch.object(admin_obj, "message_user"):
            admin_obj.reject_selected(request, reject_query)
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, Registration.Status.REJECTED)
        self.assertEqual(rejected.status_events.last().note, "Missing student ID")

    def test_mixed_bulk_approval_reports_missing_proof_without_approving_paid_entry(
        self,
    ):
        self.registration.status = Registration.Status.UNDER_REVIEW
        self.registration.save(update_fields=("status",))
        paid = Registration.objects.create(
            tournament_game=self.registration.tournament_game,
            status=Registration.Status.UNDER_REVIEW,
            fee_amount_snapshot=50000,
            fee_currency_snapshot="VND",
        )
        self.actor.groups.get().permissions.add(
            Permission.objects.get(codename="change_paymentattempt")
        )
        list_url = reverse("admin:registrations_registration_changelist")
        selected = [str(self.registration.pk), str(paid.pk)]
        response = self.client.post(
            list_url, {"action": "approve_selected", "_selected_action": selected}
        )
        self.assertContains(response, "Verify payment and approve")
        response = self.client.post(
            list_url,
            {
                "action": "approve_selected",
                "_selected_action": selected,
                "confirm_action": "1",
            },
            follow=True,
        )
        self.assertContains(response, f"Registration {paid.pk}")
        self.assertContains(response, "Payment proof is required")
        self.assertContains(response, "Approved 1 registration(s)")
        self.registration.refresh_from_db()
        paid.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.APPROVED)
        self.assertEqual(paid.status, Registration.Status.UNDER_REVIEW)

    def test_registration_table_and_detail_show_responsible_contact(self):
        self.registration.submitter_role = Registration.SubmitterRole.MANAGER
        self.registration.manager_name_snapshot = "Nguyen Manager"
        self.registration.contact_phone_snapshot = "0901234567"
        self.registration.contact_facebook_snapshot = "facebook.com/manager"
        self.registration.save()
        list_url = reverse("admin:registrations_registration_changelist")

        response = self.client.get(list_url, {"q": "0901234567"})
        self.assertEqual(response.context["cl"].result_count, 1)
        self.assertContains(response, "Nguyen Manager")
        self.assertContains(response, "0901234567")
        self.assertContains(response, "Manager")

        detail = self.client.get(self.url("change"))
        self.assertContains(detail, "Private contact")
        self.assertContains(detail, "facebook.com/manager")
        self.assertContains(detail, "Nguyen Manager")

    def test_payment_proof_is_visible_in_authorized_admin_detail(self):
        attempt = PaymentAttempt.objects.create(
            registration=self.registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            amount="50000.00",
            currency="VND",
            proof_file=payment_image(),
        )
        self.assertNotContains(
            self.client.get(self.url("change")), attempt.proof_file.url
        )
        self.actor.groups.get().permissions.add(
            Permission.objects.get(codename="view_paymentattempt")
        )
        self.actor = type(self.actor).objects.get(pk=self.actor.pk)
        self.client.force_login(self.actor)
        detail = self.client.get(self.url("change"))
        self.assertContains(detail, f'<img src="{attempt.proof_file.url}"')
        self.assertContains(detail, "object-fit:contain")
        payment_detail = self.client.get(
            reverse("admin:registrations_paymentattempt_change", args=[attempt.pk])
        )
        self.assertContains(payment_detail, f'<img src="{attempt.proof_file.url}"')

    def test_registration_table_names_captain_from_roster_snapshot(self):
        self.registration.submitter_role = Registration.SubmitterRole.CAPTAIN
        self.registration.save(update_fields=("submitter_role",))
        RegistrationMember.objects.create(
            registration=self.registration,
            display_order=1,
            is_captain=True,
            gamer_tag_snapshot="captain#1234",
            first_name_snapshot="Lan",
            last_name_snapshot="Nguyen",
            school_snapshot="HCMUS",
        )
        response = self.client.get(
            reverse("admin:registrations_registration_changelist")
        )
        self.assertContains(response, "Nguyen Lan")

    def test_admin_record_labels_identify_registration_and_related_records(self):
        self.actor.is_superuser = True
        self.actor.save(update_fields=("is_superuser",))
        member = RegistrationMember.objects.create(
            registration=self.registration,
            display_order=1,
            gamer_tag_snapshot="captain#1234",
            first_name_snapshot="Lan",
            last_name_snapshot="Nguyen",
            school_snapshot="HCMUS",
        )
        event = RegistrationStatusEvent.objects.create(
            registration=self.registration,
            to_status=Registration.Status.SUBMITTED,
        )
        attempt = PaymentAttempt.objects.create(
            registration=self.registration,
            method=PaymentAttempt.Method.MANUAL_PROOF,
            amount=0,
            currency="VND",
        )
        intent = PaymentIntent.objects.create(
            tournament_game=self.registration.tournament_game,
            registration=self.registration,
            reference="TNMT12345678",
            amount=0,
            currency="VND",
        )
        registration_label = f"Registration #{self.registration.pk} (individual)"
        self.assertContains(self.client.get(self.url("change")), registration_label)
        self.assertContains(self.client.get(self.url("change")), "Nguyen Lan")
        self.assertContains(
            self.client.get(self.url("change")), "Submitted for registration"
        )
        self.assertContains(
            self.client.get(
                reverse("admin:registrations_paymentattempt_change", args=[attempt.pk])
            ),
            f"Payment attempt #{attempt.pk} for registration #{self.registration.pk}",
        )
        self.assertContains(
            self.client.get(
                reverse("admin:registrations_paymentintent_change", args=[intent.pk])
            ),
            "Payment reference TNMT12345678",
        )
        self.assertEqual(str(member), "Nguyen Lan")
        self.assertEqual(
            str(event), f"Submitted for registration #{self.registration.pk}"
        )
