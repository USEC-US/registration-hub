import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.tests.factories import create_account
from registrations.admin_forms import PaymentSettingsForm
from registrations.bank_catalogue import (
    BankCatalogueError,
    MAX_RESPONSE_BYTES,
    fetch_bank_catalogue,
    sync_bank_catalogue,
)
from registrations.models import Bank, PaymentSettings
from registrations.tests.test_payment_settings import valid_settings


def bank_row(**overrides):
    return {
        "bin": "970415",
        "name": "Ngân hàng TMCP Công thương Việt Nam",
        "shortName": "VietinBank",
        "code": "ICB",
        "logo": "https://cdn.vietqr.io/img/ICB.png",
        "swift_code": None,
        "transferSupported": 1,
        "lookupSupported": 1,
        **overrides,
    }


def payload(*rows):
    return json.dumps({"code": "00", "data": list(rows or [bank_row()])})


class BankCatalogueTests(TestCase):
    def test_refresh_is_idempotent_and_does_not_change_payment_settings(self):
        settings = valid_settings()
        settings.save()
        first = sync_bank_catalogue(payload())
        pk = Bank.objects.get().pk
        second = sync_bank_catalogue(payload(bank_row(shortName="Updated name")))
        bank = Bank.objects.get()
        settings.refresh_from_db()
        self.assertEqual(first, {"created": 1, "updated": 0, "deactivated": 0})
        self.assertEqual(second, {"created": 0, "updated": 1, "deactivated": 0})
        self.assertEqual(bank.pk, pk)
        self.assertEqual(bank.short_name, "Updated name")
        self.assertEqual(bank.swift_code, "")
        self.assertEqual(settings.bank_name, "VietinBank")
        self.assertEqual(settings.bank_bin, "970415")

    def test_missing_banks_are_retained_and_can_be_reactivated(self):
        sync_bank_catalogue(payload())
        result = sync_bank_catalogue(payload(bank_row(bin="970436", code="VCB")))
        self.assertEqual(result["deactivated"], 1)
        self.assertFalse(Bank.objects.get(bin="970415").is_active)
        sync_bank_catalogue(payload())
        self.assertTrue(Bank.objects.get(bin="970415").is_active)

    def test_invalid_responses_leave_entire_catalogue_unchanged(self):
        sync_bank_catalogue(payload())
        before = list(Bank.objects.values())
        cases = [
            "not json",
            json.dumps({"code": "99", "data": [bank_row()]}),
            json.dumps({"code": "00", "data": []}),
            payload(bank_row(), bank_row()),
            payload(bank_row(bin="097041"), bank_row(bin="invalid")),
            payload(bank_row(bin=970415)),
            payload(bank_row(shortName="")),
            payload(bank_row(transferSupported=2)),
            payload(bank_row(name="x" * 256)),
        ]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(BankCatalogueError):
                sync_bank_catalogue(body)
            self.assertEqual(list(Bank.objects.values()), before)

    def test_dry_run_does_not_write(self):
        self.assertEqual(sync_bank_catalogue(payload(), dry_run=True)["created"], 1)
        self.assertFalse(Bank.objects.exists())

    @patch("registrations.bank_catalogue.urlopen")
    def test_network_failure_preserves_saved_catalogue(self, urlopen):
        sync_bank_catalogue(payload())
        before = list(Bank.objects.values())
        for error in (URLError("offline"), TimeoutError("timeout")):
            urlopen.side_effect = error
            with self.assertRaises(BankCatalogueError):
                sync_bank_catalogue()
            self.assertEqual(list(Bank.objects.values()), before)

    @patch("registrations.bank_catalogue.urlopen")
    def test_fetch_limits_response_size(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b"x" * (
            MAX_RESPONSE_BYTES + 1
        )
        with self.assertRaises(BankCatalogueError):
            fetch_bank_catalogue()
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 15)

    def test_database_failure_rolls_back_all_rows(self):
        original = Bank.objects.update_or_create

        def fail_second(*args, **kwargs):
            if kwargs["bin"] == "970436":
                raise IntegrityError("simulated failure")
            return original(*args, **kwargs)

        with patch.object(Bank.objects, "update_or_create", side_effect=fail_second):
            with self.assertRaises(IntegrityError):
                sync_bank_catalogue(payload(bank_row(), bank_row(bin="970436")))
        self.assertFalse(Bank.objects.exists())

    def test_command_imports_file_and_reports_validation_errors(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "banks.json"
            path.write_text(payload())
            output = StringIO()
            call_command("sync_banks", file=path, dry_run=True, stdout=output)
            self.assertIn("Dry run: 1 new", output.getvalue())
            self.assertFalse(Bank.objects.exists())
            call_command("sync_banks", file=path, stdout=StringIO())
            self.assertEqual(Bank.objects.count(), 1)
            path.write_text("invalid")
            with self.assertRaises(CommandError):
                call_command("sync_banks", file=path)


class BankSelectionTests(TestCase):
    def form(self, *, instance=None, **overrides):
        return PaymentSettingsForm(
            data={
                "enabled": True,
                "bank_bin": "970415",
                "bank_name": "Tampered name",
                "account_number": "00001234",
                "account_holder": "HCMUSEC",
                "payment_hold_minutes": 60,
                **overrides,
            },
            instance=instance,
        )

    def test_selection_derives_bank_name_and_preserves_account_zeroes(self):
        sync_bank_catalogue(payload())
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        settings = form.save()
        self.assertEqual(settings.bank_name, "VietinBank")
        self.assertEqual(settings.bank_bin, "970415")
        self.assertEqual(settings.account_number, "00001234")

    def test_existing_unknown_bank_survives_empty_catalogue(self):
        settings = valid_settings()
        settings.save()
        form = self.form(instance=settings)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().bank_name, "VietinBank")

    def test_inactive_bank_only_available_to_existing_settings(self):
        sync_bank_catalogue(payload())
        Bank.objects.update(is_active=False)
        fresh = self.form()
        self.assertFalse(fresh.is_valid())
        self.assertIn("bank_bin", fresh.errors)
        existing = self.form(instance=valid_settings())
        self.assertTrue(existing.is_valid(), existing.errors)

    def test_scanning_support_flag_does_not_block_receiving_bank_selection(self):
        sync_bank_catalogue(payload(bank_row(transferSupported=0)))
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)

    def test_disabled_blank_settings_are_valid_and_enabled_blank_are_not(self):
        disabled = self.form(
            enabled=False, bank_bin="", account_number="", account_holder=""
        )
        self.assertTrue(disabled.is_valid(), disabled.errors)
        enabled = self.form(bank_bin="")
        self.assertFalse(enabled.is_valid())
        self.assertIn("bank_bin", enabled.errors)


class BankAdminTests(TestCase):
    def setUp(self):
        call_command("bootstrap_organizers", stdout=StringIO())
        self.user = create_account(
            email="bank-admin@example.com",
            password="strong-password",
            first_name="Bank",
            last_name="Admin",
            is_staff=True,
        )
        self.user.groups.add(Group.objects.get(name="Organizers"))
        self.client.force_login(self.user)
        self.list_url = reverse("admin:registrations_bank_changelist")
        self.sync_url = reverse("admin:registrations_bank_sync")

    def test_catalogue_and_settings_pages_render_with_search_and_refresh(self):
        sync_bank_catalogue(payload())
        response = self.client.get(self.list_url, {"q": "970415"})
        self.assertContains(response, "VietinBank")
        self.assertContains(response, "Refresh bank catalogue")
        self.assertContains(
            self.client.get(reverse("admin:registrations_paymentsettings_add")),
            "VietinBank",
        )
        self.assertNotContains(
            self.client.get(self.list_url, {"q": "nonexistent"}), "VietinBank"
        )

    @patch("registrations.bank_catalogue.fetch_bank_catalogue", return_value=payload())
    def test_refresh_requires_post_and_updates_catalogue(self, fetch):
        self.assertEqual(self.client.get(self.sync_url).status_code, 405)
        fetch.assert_not_called()
        response = self.client.post(self.sync_url, follow=True)
        self.assertContains(response, "Bank catalogue refreshed: 1 new")
        self.assertEqual(Bank.objects.count(), 1)

    @patch(
        "registrations.admin.sync_bank_catalogue",
        side_effect=BankCatalogueError("Unavailable"),
    )
    def test_refresh_failure_displays_error(self, sync):
        self.assertContains(self.client.post(self.sync_url, follow=True), "Unavailable")

    @patch("registrations.admin.sync_bank_catalogue")
    def test_unprivileged_staff_cannot_refresh_or_view(self, sync):
        self.user.groups.clear()
        self.user.user_permissions.add(
            *Permission.objects.filter(codename__in=("view_bank", "change_bank"))
        )
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.post(self.sync_url).status_code, 403)
        sync.assert_not_called()

    @patch("registrations.admin.sync_bank_catalogue")
    def test_view_only_organizer_cannot_refresh(self, sync):
        Group.objects.get(name="Organizers").permissions.remove(
            Permission.objects.get(codename="change_bank")
        )
        self.assertNotContains(self.client.get(self.list_url), "Refresh bank catalogue")
        self.assertEqual(self.client.post(self.sync_url).status_code, 403)
        sync.assert_not_called()

    def test_refresh_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.sync_url).status_code, 403)

    def test_payment_settings_admin_saves_bank_selection(self):
        sync_bank_catalogue(payload())
        response = self.client.post(
            reverse("admin:registrations_paymentsettings_add"),
            {
                "enabled": "on",
                "bank_bin": "970415",
                "bank_name": "Tampered name",
                "account_number": "00001234",
                "account_holder": "HCMUSEC",
                "payment_hold_minutes": "60",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PaymentSettings.objects.get().bank_name, "VietinBank")
