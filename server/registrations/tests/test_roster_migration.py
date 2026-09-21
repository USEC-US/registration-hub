from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RosterMigrationTests(TransactionTestCase):
    old_targets = [
        ("tournaments", "0002_tournament_cover_image_tournament_is_featured"),
        ("registrations", "0002_registration_contact_discord_snapshot_and_more"),
    ]
    new_targets = [
        ("tournaments", "0003_main_roster_and_substitutes"),
        ("registrations", "0003_member_roster_role"),
    ]

    def test_existing_limits_and_submitted_snapshots_survive_forward_and_reverse(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.old_targets)
        self.addCleanup(
            lambda: MigrationExecutor(connection).migrate(
                MigrationExecutor(connection).loader.graph.leaf_nodes()
            )
        )
        apps = executor.loader.project_state(self.old_targets).apps
        tournament = apps.get_model("tournaments", "Tournament").objects.create(
            name="Legacy", slug="legacy"
        )
        game = apps.get_model("tournaments", "Game").objects.create(
            name="Legacy", slug="legacy"
        )
        division = apps.get_model("tournaments", "TournamentGame").objects.create(
            tournament=tournament,
            game=game,
            team_size_min=2,
            team_size_max=3,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount=0,
            fee_currency="VND",
        )
        registration = apps.get_model("registrations", "Registration").objects.create(
            tournament_game=division,
            team_name="Legacy Team",
            status="SUBMITTED",
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        member_model = apps.get_model("registrations", "RegistrationMember")
        for index in (1, 2, 3):
            member_model.objects.create(
                registration=registration,
                gamer_tag_snapshot=f"Player {index}",
                school_snapshot="Historical institution",
                display_order=index,
                is_captain=index == 3,
            )
        executor = MigrationExecutor(connection)
        executor.migrate(self.new_targets)
        apps = executor.loader.project_state(self.new_targets).apps
        migrated = apps.get_model("tournaments", "TournamentGame").objects.get(
            pk=division.pk
        )
        self.assertEqual((migrated.main_roster_size, migrated.substitute_limit), (2, 1))
        members = list(
            apps.get_model("registrations", "RegistrationMember").objects.order_by(
                "display_order"
            )
        )
        self.assertEqual(
            [m.roster_role for m in members], ["main", "main", "substitute"]
        )
        self.assertEqual(
            [m.gamer_tag_snapshot for m in members],
            ["Player 1", "Player 2", "Player 3"],
        )
        self.assertEqual(
            [m.school_snapshot for m in members], ["Historical institution"] * 3
        )
        self.assertTrue(members[2].is_captain)
        executor = MigrationExecutor(connection)
        executor.migrate(self.old_targets)
        apps = executor.loader.project_state(self.old_targets).apps
        restored = apps.get_model("tournaments", "TournamentGame").objects.get(
            pk=division.pk
        )
        self.assertEqual((restored.team_size_min, restored.team_size_max), (2, 3))
