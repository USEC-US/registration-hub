from datetime import timedelta

from django.db import IntegrityError, connection, transaction
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


class RoundRobinMigrationTests(TransactionTestCase):
    def test_populated_upgrade_preserves_results_modes_and_round_uniqueness(self):
        old_target = [("competitions", "0002_double_elimination")]
        new_target = [("competitions", "0003_round_robin")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_target)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        apps = executor.loader.project_state(old_target).apps
        tournament = apps.get_model("tournaments", "Tournament").objects.create(
            name="Migration cup", slug="migration-cup"
        )
        game = apps.get_model("tournaments", "Game").objects.create(
            name="Migration chess", slug="migration-chess"
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
        stage = apps.get_model("competitions", "Stage").objects.create(
            competition=competition,
            sequence=1,
            name="Legacy",
            format="SINGLE_ELIMINATION",
            series_mode="BEST_OF",
            default_series_length=3,
        )
        draw = apps.get_model("competitions", "StageDraw").objects.create(
            stage=stage, version=1
        )
        round_ = apps.get_model("competitions", "Round").objects.create(
            draw=draw, number=1
        )
        match = apps.get_model("competitions", "Match").objects.create(
            round=round_,
            number=1,
            code="migration-match",
            status="FINAL",
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=1,
            applied_series_length=3,
            started_at=timezone.now(),
        )
        MigrationExecutor(connection).migrate(new_target)
        apps = MigrationExecutor(connection).loader.project_state(new_target).apps
        migrated = apps.get_model("competitions", "Match").objects.get(pk=match.pk)
        self.assertEqual(
            (
                migrated.side_one_score,
                migrated.side_two_score,
                migrated.applied_series_mode,
            ),
            (2, 1, "BEST_OF"),
        )
        round_model = apps.get_model("competitions", "Round")
        self.assertEqual(round_model.objects.get(pk=round_.pk).draw_id, draw.pk)
        for number, name in enumerate(("A", "B"), 1):
            group = apps.get_model("competitions", "StageGroup").objects.create(
                draw_id=draw.pk, number=number, name=name, qualifying_places=1
            )
            round_model.objects.create(draw_id=draw.pk, group=group, number=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            round_model.objects.create(draw_id=draw.pk, number=1)


class MultiStageMigrationTests(TransactionTestCase):
    def test_populated_0003_upgrade_preserves_draws_and_backfills_rules(self):
        old_target = [("competitions", "0003_round_robin")]
        new_target = [("competitions", "0004_multi_stage")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_target)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        apps = executor.loader.project_state(old_target).apps

        def model(name):
            return apps.get_model("competitions", name)

        tournament = apps.get_model("tournaments", "Tournament").objects.create(
            name="Multi migration", slug="multi-migration"
        )
        game = apps.get_model("tournaments", "Game").objects.create(
            name="Multi game", slug="multi-game"
        )
        division = apps.get_model("tournaments", "TournamentGame").objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount=0,
            fee_currency="VND",
        )
        competition = model("Competition").objects.create(tournament_game=division)
        published_at = timezone.now()
        stage = model("Stage").objects.create(
            competition=competition,
            sequence=1,
            name="Groups",
            format="ROUND_ROBIN",
            series_mode="BEST_OF",
            default_series_length=1,
            published_at=published_at,
        )
        old = model("StageDraw").objects.create(
            stage=stage, version=1, state="SUPERSEDED"
        )
        current = model("StageDraw").objects.create(
            stage=stage, version=2, state="PUBLISHED", published_at=published_at
        )
        model("StageGroup").objects.create(
            draw=old, number=1, name="Old", qualifying_places=1
        )
        group = model("StageGroup").objects.create(
            draw=current, number=1, name="A", qualifying_places=2
        )
        for index in range(3):
            registration = apps.get_model(
                "registrations", "Registration"
            ).objects.create(
                tournament_game=division,
                status="APPROVED",
                fee_amount_snapshot=0,
                fee_currency_snapshot="VND",
            )
            entrant = model("CompetitionEntrant").objects.create(
                competition=competition,
                registration=registration,
                display_name=f"Team {index}",
            )
            model("StageEntry").objects.create(
                draw=current, entrant=entrant, seed=index + 1, group=group
            )
        tie = model("TieResolution").objects.create(
            group=group,
            method="EXTRA_MATCHES",
            state="CONFIRMED",
            source_fingerprint="a" * 64,
            places=1,
        )
        nested = model("TieResolution").objects.create(
            group=group,
            parent=tie,
            method="MANUAL",
            state="CONFIRMED",
            source_fingerprint="b" * 64,
            places=1,
        )
        round_ = model("Round").objects.create(draw=current, group=group, number=1)
        match = model("Match").objects.create(
            round=round_,
            number=1,
            code="legacy-code",
            status="FINAL",
            outcome="PLAYED",
            side_one_score=1,
            side_two_score=0,
            applied_series_length=1,
        )
        MigrationExecutor(connection).migrate(new_target)
        apps = MigrationExecutor(connection).loader.project_state(new_target).apps
        plans = apps.get_model("competitions", "StageGroupPlan").objects
        self.assertEqual(
            list(plans.values_list("name", "size", "qualifying_places")), [("A", 3, 2)]
        )
        ties = apps.get_model("competitions", "TieResolution").objects
        self.assertEqual(ties.get(pk=tie.pk).draw_id, current.pk)
        self.assertEqual(ties.get(pk=nested.pk).parent_id, tie.pk)
        self.assertEqual(ties.get(pk=nested.pk).draw_id, current.pk)
        migrated = apps.get_model("competitions", "Match").objects.get(pk=match.pk)
        self.assertEqual(
            (migrated.code, migrated.side_one_score, migrated.side_two_score),
            ("legacy-code", 1, 0),
        )
        self.assertEqual(
            apps.get_model("competitions", "Stage")
            .objects.get(pk=stage.pk)
            .published_at,
            published_at,
        )
        draws = apps.get_model("competitions", "StageDraw").objects
        self.assertEqual(draws.get(pk=old.pk).state, "SUPERSEDED")
        self.assertEqual(draws.get(pk=current.pk).published_at, published_at)
