from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class PaymentReservationMigrationTests(TransactionTestCase):
    def test_historical_payments_do_not_gain_deadlines_or_bank_destinations(self):
        old_target = [
            ("registrations", "0008_alter_paymentintent_transfer_content_template"),
            ("tournaments", "0005_tournament_transfer_content_limit_and_more"),
        ]
        new_target = [
            ("registrations", "0009_payment_settings_and_reservations"),
            ("tournaments", "0005_tournament_transfer_content_limit_and_more"),
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_target)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        old_apps = executor.loader.project_state(old_target).apps
        tournament = old_apps.get_model("tournaments", "Tournament").objects.create(
            name="Historical Tournament",
            slug="historical-tournament",
            transfer_content_template="{participant} payment",
            transfer_content_limit=100,
        )
        game = old_apps.get_model("tournaments", "Game").objects.create(
            name="Historical Game", slug="historical-game"
        )
        division = old_apps.get_model("tournaments", "TournamentGame").objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="50000.00",
            fee_currency="VND",
        )
        registration = old_apps.get_model(
            "registrations", "Registration"
        ).objects.create(
            tournament_game=division,
            status="SUBMITTED",
            fee_amount_snapshot="50000.00",
            fee_currency_snapshot="VND",
        )
        intent = old_apps.get_model("registrations", "PaymentIntent").objects.create(
            reference="USECHISTORY123",
            tournament_game=division,
            registration=registration,
            amount="50000.00",
            currency="VND",
            transfer_content="HISTORY",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        migrated_registration = new_apps.get_model(
            "registrations", "Registration"
        ).objects.get(pk=registration.pk)
        migrated_intent = new_apps.get_model(
            "registrations", "PaymentIntent"
        ).objects.get(pk=intent.pk)

        self.assertIsNone(migrated_registration.payment_due_at)
        self.assertIsNone(migrated_registration.payment_hold_minutes_snapshot)
        self.assertEqual(migrated_intent.bank_name_snapshot, "")
        self.assertEqual(migrated_intent.bank_bin_snapshot, "")
        self.assertEqual(migrated_intent.account_number_snapshot, "")
        self.assertEqual(migrated_intent.account_holder_snapshot, "")
        self.assertEqual(migrated_intent.transfer_content, "HISTORY")
        self.assertEqual(
            new_apps.get_model("registrations", "PaymentSettings").objects.count(),
            0,
        )
