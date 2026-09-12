from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class PlayerDetailsMigrationTests(TransactionTestCase):
    def test_legacy_registrations_keep_unknown_identity_details_empty(self):
        old_targets = [
            ("registrations", "0003_member_roster_role"),
            ("tournaments", "0003_main_roster_and_substitutes"),
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_targets)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        apps = executor.loader.project_state(old_targets).apps
        tournament = apps.get_model("tournaments", "Tournament").objects.create(
            name="Legacy", slug="legacy"
        )
        game = apps.get_model("tournaments", "Game").objects.create(
            name="Legacy", slug="legacy"
        )
        division = apps.get_model("tournaments", "TournamentGame").objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount=0,
        )
        registration = apps.get_model("registrations", "Registration").objects.create(
            tournament_game=division,
            status="SUBMITTED",
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        member = apps.get_model("registrations", "RegistrationMember").objects.create(
            registration=registration,
            gamer_tag_snapshot="Historical player",
            school_snapshot="Historical institution",
            is_captain=True,
            roster_role="main",
            display_order=1,
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        migrated = apps.get_model("registrations", "RegistrationMember").objects.get(
            pk=member.pk
        )
        self.assertEqual(migrated.first_name_snapshot, "")
        self.assertEqual(migrated.last_name_snapshot, "")
        self.assertIsNone(migrated.date_of_birth_snapshot)
        self.assertEqual(migrated.student_id_snapshot, "")
        self.assertEqual(migrated.gamer_tag_snapshot, "Historical player")
        self.assertEqual(migrated.school_snapshot, "Historical institution")
        self.assertFalse(
            apps.get_model("tournaments", "Tournament")
            .objects.get(pk=tournament.pk)
            .students_only
        )
