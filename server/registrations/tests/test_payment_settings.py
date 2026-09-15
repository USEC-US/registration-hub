from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from accounts.tests.factories import create_account
from registrations.admin import PaymentSettingsAdmin
from registrations.models import PaymentSettings
from registrations.payment_settings import require_payment_settings


def valid_settings(**overrides):
    values = {
        "enabled": True,
        "bank_name": "VietinBank",
        "bank_bin": "970415",
        "account_number": "0011001932418",
        "account_holder": "HCMUSEC",
        "payment_hold_minutes": 60,
    }
    values.update(overrides)
    return PaymentSettings(**values)


class PaymentSettingsValidationTests(TestCase):
    def test_disabled_blank_settings_are_valid_but_unavailable(self):
        settings = PaymentSettings()
        settings.full_clean()
        settings.save()

        with self.assertRaises(ValidationError):
            require_payment_settings(amount=Decimal("50000"), currency="VND")

    def test_missing_settings_are_not_created_as_a_side_effect(self):
        with self.assertRaises(ValidationError):
            require_payment_settings(amount=Decimal("50000"), currency="VND")

        self.assertEqual(PaymentSettings.objects.count(), 0)

    def test_enabled_settings_require_a_complete_supported_destination(self):
        for field in ("bank_name", "bank_bin", "account_number", "account_holder"):
            with self.subTest(field=field):
                settings = valid_settings(**{field: ""})
                with self.assertRaises(ValidationError) as error:
                    settings.full_clean()
                self.assertIn(field, error.exception.message_dict)
        for field, value in (
            ("bank_bin", "97041A"),
            ("account_number", "0011 0019"),
            ("account_number", "1" * 20),
        ):
            with self.subTest(field=field, value=value):
                settings = valid_settings(**{field: value})
                with self.assertRaises(ValidationError) as error:
                    settings.full_clean()
                self.assertIn(field, error.exception.message_dict)

    def test_singleton_identity_and_duration_are_database_constraints(self):
        valid_settings().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            valid_settings(pk=2).save(force_insert=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentSettings.objects.filter(pk=1).update(payment_hold_minutes=14)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentSettings.objects.filter(pk=1).update(payment_hold_minutes=1441)

    def test_service_returns_enabled_settings_and_preserves_leading_zeroes(self):
        settings = valid_settings(account_number="00001234")
        settings.full_clean()
        settings.save()

        result = require_payment_settings(amount=Decimal("50000"), currency="VND")

        self.assertEqual(result.pk, 1)
        self.assertEqual(result.account_number, "00001234")

    def test_service_rejects_unsupported_or_invalid_amounts(self):
        valid_settings().save()
        cases = (
            (Decimal("50000"), "USD"),
            (Decimal("0"), "VND"),
            (Decimal("-1"), "VND"),
            (Decimal("1.5"), "VND"),
            (Decimal("10000000000000"), "VND"),
        )
        for amount, currency in cases:
            with self.subTest(amount=amount, currency=currency):
                with self.assertRaises(ValidationError):
                    require_payment_settings(amount=amount, currency=currency)


class PaymentSettingsAdminTests(TestCase):
    def setUp(self):
        self.admin = PaymentSettingsAdmin(PaymentSettings, AdminSite())
        self.factory = RequestFactory()

    def request_for(self, user):
        request = self.factory.get("/admin/registrations/paymentsettings/")
        request.user = user
        return request

    def user(self, email, *, organizer=False, superuser=False, permissions=()):
        user = create_account(
            email=email,
            password="strong-password",
            first_name="Payment",
            last_name="Editor",
            is_staff=True,
            is_superuser=superuser,
        )
        if organizer:
            group, _ = Group.objects.get_or_create(name="Organizers")
            user.groups.add(group)
        if permissions:
            user.user_permissions.add(
                *Permission.objects.filter(
                    content_type__app_label="registrations",
                    codename__in=permissions,
                )
            )
        return user

    def test_ordinary_staff_cannot_bypass_organizer_membership_with_permissions(self):
        user = self.user(
            "ordinary@example.com",
            permissions=(
                "add_paymentsettings",
                "change_paymentsettings",
                "view_paymentsettings",
            ),
        )
        request = self.request_for(user)

        self.assertFalse(self.admin.has_module_permission(request))
        self.assertFalse(self.admin.has_add_permission(request))
        self.assertFalse(self.admin.has_change_permission(request))
        self.assertFalse(self.admin.has_view_permission(request))

    def test_organizer_without_model_permission_cannot_edit_settings(self):
        request = self.request_for(self.user("limited@example.com", organizer=True))

        self.assertFalse(self.admin.has_add_permission(request))
        self.assertFalse(self.admin.has_change_permission(request))
        self.assertFalse(self.admin.has_view_permission(request))

    def test_authorized_organizer_can_create_once_and_change_but_not_delete(self):
        user = self.user(
            "authorized@example.com",
            organizer=True,
            permissions=(
                "add_paymentsettings",
                "change_paymentsettings",
                "view_paymentsettings",
            ),
        )
        request = self.request_for(user)

        self.assertTrue(self.admin.has_add_permission(request))
        self.assertTrue(self.admin.has_change_permission(request))
        self.assertTrue(self.admin.has_view_permission(request))
        self.assertFalse(self.admin.has_delete_permission(request))
        valid_settings().save()
        self.assertFalse(self.admin.has_add_permission(request))

    def test_superuser_can_manage_settings_but_not_delete_them(self):
        request = self.request_for(self.user("super@example.com", superuser=True))

        self.assertTrue(self.admin.has_add_permission(request))
        self.assertTrue(self.admin.has_change_permission(request))
        self.assertTrue(self.admin.has_view_permission(request))
        self.assertFalse(self.admin.has_delete_permission(request))
