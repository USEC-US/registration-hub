from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class DoubleEliminationMigrationTests(TransactionTestCase):
    def test_legacy_double_elimination_stages_default_to_reset(self):
        old_target = [("competitions", "0001_initial")]
        new_target = [("competitions", "0002_double_elimination")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_target)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        apps = executor.loader.project_state(old_target).apps

        tournament = apps.get_model("tournaments", "Tournament").objects.create(
            name="Legacy Cup", slug="legacy-cup"
        )
        game = apps.get_model("tournaments", "Game").objects.create(
            name="Legacy Game", slug="legacy-game"
        )
        division = apps.get_model("tournaments", "TournamentGame").objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount=0,
            fee_currency="VND",
        )
        competition = apps.get_model("competitions", "Competition").objects.create(
            tournament_game=division
        )
        stage_model = apps.get_model("competitions", "Stage")
        single = stage_model.objects.create(
            competition=competition,
            sequence=1,
            name="Single",
            format="SINGLE_ELIMINATION",
            series_mode="BEST_OF",
            default_series_length=3,
        )
        double = stage_model.objects.create(
            competition=competition,
            sequence=2,
            name="Double",
            format="DOUBLE_ELIMINATION",
            series_mode="BEST_OF",
            default_series_length=3,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        apps = executor.loader.project_state(new_target).apps
        migrated_stages = apps.get_model("competitions", "Stage").objects

        self.assertEqual(migrated_stages.get(pk=double.pk).grand_final_policy, "RESET")
        self.assertEqual(migrated_stages.get(pk=single.pk).grand_final_policy, "")
