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


class SwissMigrationTests(TransactionTestCase):
    def test_round_migration_preserves_legacy_publication(self):
        old_target = [("competitions", "0004_multi_stage")]
        new_target = [("competitions", "0005_swiss")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_target)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        apps = executor.loader.project_state(old_target).apps

        def model(name):
            return apps.get_model("competitions", name)

        tournament = apps.get_model("tournaments", "Tournament").objects.create(
            name="Swiss upgrade", slug="swiss-upgrade", is_published=True
        )
        game = apps.get_model("tournaments", "Game").objects.create(
            name="Swiss game", slug="swiss-game"
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
        stage = model("Stage").objects.create(
            competition=competition,
            sequence=1,
            name="Legacy groups",
            format="ROUND_ROBIN",
            series_mode="BEST_OF",
            default_series_length=3,
        )
        timestamp = timezone.now() - timedelta(days=3)
        private_retired = model("StageDraw").objects.create(
            stage=stage, version=1, state="SUPERSEDED"
        )
        public_retired = model("StageDraw").objects.create(
            stage=stage, version=2, state="SUPERSEDED", published_at=timestamp
        )
        published = model("StageDraw").objects.create(
            stage=stage, version=3, state="PUBLISHED", published_at=timestamp
        )
        next_stage = model("Stage").objects.create(
            competition=competition,
            sequence=2,
            name="Next bracket",
            format="SINGLE_ELIMINATION",
            series_mode="BEST_OF",
            default_series_length=3,
            advancement_count=2,
        )
        draft = model("StageDraw").objects.create(
            stage=next_stage,
            version=1,
            source_draw=published,
            source_fingerprint="a" * 64,
        )
        group = model("StageGroup").objects.create(
            draw=published, number=1, name="Legacy A", qualifying_places=2
        )
        plan = model("StageGroupPlan").objects.create(
            stage=stage, number=1, name="Legacy A", size=3, qualifying_places=2
        )
        rounds = {}
        for name, draw in (
            ("draft", draft),
            ("published", published),
            ("retired_public", public_retired),
            ("retired_private", private_retired),
        ):
            rounds[name] = model("Round").objects.create(draw=draw, number=1)
        rounds["grouped"] = model("Round").objects.create(
            draw=published, group=group, number=1
        )
        ties = []
        for number, state in enumerate(("PENDING", "SUPERSEDED"), 1):
            tie = model("TieResolution").objects.create(
                draw=published,
                group=group,
                method="EXTRA_MATCHES",
                state=state,
                source_fingerprint=str(number) * 64,
                places=1,
                parent=ties[0] if ties else None,
            )
            ties.append(tie)
            rounds[f"tie_{state}"] = model("Round").objects.create(
                draw=published,
                group=group,
                number=number,
                section="TIEBREAK",
                tie_resolution=tie,
            )
        registration = apps.get_model("registrations", "Registration").objects.create(
            tournament_game=division,
            status="APPROVED",
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        entrant = model("CompetitionEntrant").objects.create(
            competition=competition,
            registration=registration,
            display_name="Saved entrant",
        )
        entry = model("StageEntry").objects.create(
            draw=published, entrant=entrant, seed=1, group=group
        )
        later_entry = model("StageEntry").objects.create(
            draw=draft, entrant=entrant, seed=1, source_entry=entry
        )
        ties[0].contenders.add(entry)
        match = model("Match").objects.create(
            round=rounds["grouped"],
            number=1,
            code="Stored Đ-M9",
            status="FINAL",
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=1,
            winner=entry,
            applied_series_mode="BEST_OF",
            applied_series_length=3,
        )
        direct_slot = model("MatchSlot").objects.create(
            match=match, position=1, entry=entry, is_resolved=True, resolved_entry=entry
        )
        other_registration = apps.get_model(
            "registrations", "Registration"
        ).objects.create(
            tournament_game=division,
            status="APPROVED",
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        other_entrant = model("CompetitionEntrant").objects.create(
            competition=competition,
            registration=other_registration,
            display_name="Opponent",
        )
        other_entry = model("StageEntry").objects.create(
            draw=published, entrant=other_entrant, seed=2, group=group
        )
        other_slot = model("MatchSlot").objects.create(
            match=match,
            position=2,
            entry=other_entry,
            is_resolved=True,
            resolved_entry=other_entry,
        )
        bye = model("Match").objects.create(
            round=rounds["draft"],
            number=1,
            code="Saved bye-M1",
            status="FINAL",
            outcome="BYE",
            winner=later_entry,
        )
        model("MatchSlot").objects.create(
            match=bye,
            position=1,
            entry=later_entry,
            is_resolved=True,
            resolved_entry=later_entry,
        )
        empty_slot = model("MatchSlot").objects.create(
            match=bye, position=2, is_empty=True, is_resolved=True
        )
        current_extra = model("Match").objects.create(
            round=rounds["tie_PENDING"], number=1, code="Pending extra-M11"
        )
        for position, contender in enumerate((entry, other_entry), 1):
            model("MatchSlot").objects.create(
                match=current_extra,
                position=position,
                entry=contender,
                is_resolved=True,
                resolved_entry=contender,
            )
        extra = model("Match").objects.create(
            round=rounds["tie_SUPERSEDED"],
            number=1,
            code="Stored extra-M10",
            status="FINAL",
            outcome="FORFEIT",
            winner=entry,
        )
        source_slot = model("MatchSlot").objects.create(
            match=extra,
            position=1,
            source_match=match,
            source_outcome="WINNER",
            is_resolved=True,
            resolved_entry=entry,
        )
        placeholder = model("Stage").objects.create(
            competition=competition,
            sequence=3,
            name="Legacy Swiss",
            format="SWISS_THRESHOLD",
            series_mode="BEST_OF",
            default_series_length=1,
        )
        MigrationExecutor(connection).migrate(new_target)
        apps = MigrationExecutor(connection).loader.project_state(new_target).apps
        new_match = model("Match").objects.get(pk=match.pk)
        self.assertEqual((new_match.side_one_score, new_match.winner_id), (2, entry.pk))
        self.assertEqual(
            (new_match.code, new_match.status, new_match.outcome),
            ("Stored Đ-M9", "FINAL", "PLAYED"),
        )
        migrated_extra = model("Match").objects.get(pk=extra.pk)
        self.assertEqual(
            (
                migrated_extra.code,
                migrated_extra.status,
                migrated_extra.outcome,
                migrated_extra.winner_id,
            ),
            ("Stored extra-M10", "FINAL", "FORFEIT", entry.pk),
        )
        self.assertEqual(
            list(
                model("TieResolution")
                .objects.get(pk=ties[0].pk)
                .contenders.values_list("pk", flat=True)
            ),
            [entry.pk],
        )
        self.assertEqual(
            model("TieResolution").objects.get(pk=ties[1].pk).parent_id, ties[0].pk
        )
        self.assertEqual(
            model("Match").objects.get(pk=current_extra.pk).code, "Pending extra-M11"
        )
        self.assertEqual(model("StageGroup").objects.get(pk=group.pk).name, "Legacy A")
        self.assertEqual(
            model("StageEntry").objects.get(pk=later_entry.pk).source_entry_id, entry.pk
        )
        self.assertEqual(
            model("StageDraw").objects.get(pk=draft.pk).source_draw_id, published.pk
        )
        self.assertEqual(
            model("StageDraw").objects.get(pk=draft.pk).source_fingerprint, "a" * 64
        )
        self.assertEqual(model("StageGroupPlan").objects.get(pk=plan.pk).size, 3)
        self.assertEqual(
            model("StageGroupPlan").objects.get(pk=plan.pk).qualifying_places, 2
        )
        self.assertEqual(
            model("Stage").objects.get(pk=next_stage.pk).advancement_count, 2
        )
        for slot in (direct_slot, other_slot, empty_slot, source_slot):
            migrated = model("MatchSlot").objects.get(pk=slot.pk)
            self.assertEqual(
                (
                    migrated.entry_id,
                    migrated.source_match_id,
                    migrated.is_empty,
                    migrated.is_resolved,
                    migrated.resolved_entry_id,
                ),
                (
                    slot.entry_id,
                    slot.source_match_id,
                    slot.is_empty,
                    slot.is_resolved,
                    slot.resolved_entry_id,
                ),
            )
        for name, old in rounds.items():
            new = model("Round").objects.get(pk=old.pk)
            retired = name.startswith("retired_") or name == "tie_SUPERSEDED"
            public = name not in ("draft", "retired_private")
            self.assertEqual(
                new.state,
                "SUPERSEDED" if retired else "PUBLISHED" if public else "DRAFT",
            )
            self.assertEqual(new.published_at, timestamp if public else None)
            self.assertEqual(
                (new.version, new.draw_id, new.group_id, new.tie_resolution_id),
                (1, old.draw_id, old.group_id, old.tie_resolution_id),
            )
        migrated_placeholder = model("Stage").objects.get(pk=placeholder.pk)
        self.assertIsNone(migrated_placeholder.swiss_win_target)
        self.assertIsNone(migrated_placeholder.swiss_loss_limit)
        self.assertIsNone(migrated_placeholder.advancement_count)


class CompetitionLifecycleMigrationTests(TransactionTestCase):
    def test_lifecycle_upgrade_preserves_competition_history(self):
        old_target = [("competitions", "0005_swiss")]
        new_target = [("competitions", "0006_competition_lifecycle")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_target)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        apps = executor.loader.project_state(old_target).apps

        def model(name):
            return apps.get_model("competitions", name)

        tournament = apps.get_model("tournaments", "Tournament").objects.create(
            name="Lifecycle upgrade", slug="lifecycle-upgrade", is_published=True
        )
        game = apps.get_model("tournaments", "Game").objects.create(
            name="Lifecycle game", slug="lifecycle-game"
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
        source_stage = model("Stage").objects.create(
            competition=competition,
            sequence=1,
            name="Qualifier",
            format="ROUND_ROBIN",
            series_mode="BEST_OF",
            default_series_length=3,
        )
        source_draw = model("StageDraw").objects.create(stage=source_stage, version=1)
        source_round = model("Round").objects.create(draw=source_draw, number=1)
        stage = model("Stage").objects.create(
            competition=competition,
            sequence=2,
            name="Swiss",
            format="SWISS_FIXED",
            series_mode="BEST_OF",
            default_series_length=3,
            advancement_count=2,
            swiss_round_count=3,
        )
        timestamp = timezone.now() - timedelta(days=2)
        draw = model("StageDraw").objects.create(
            stage=stage,
            version=1,
            state="PUBLISHED",
            published_at=timestamp,
            swiss_round_limit=3,
            source_draw=source_draw,
            source_fingerprint="a" * 64,
        )
        entries = []
        for seed, status in ((1, "ACTIVE"), (2, "WITHDRAWN")):
            registration = apps.get_model(
                "registrations", "Registration"
            ).objects.create(
                tournament_game=division,
                status="APPROVED" if seed == 1 else "REJECTED",
                fee_amount_snapshot=0,
                fee_currency_snapshot="VND",
            )
            entrant = model("CompetitionEntrant").objects.create(
                competition=competition,
                registration=registration,
                display_name=f"Entrant {seed}",
                status=status,
                is_selected=seed == 1,
            )
            entries.append(
                model("StageEntry").objects.create(
                    draw=draw,
                    entrant=entrant,
                    seed=seed,
                    source_entry=model("StageEntry").objects.create(
                        draw=source_draw, entrant=entrant, seed=seed
                    ),
                )
            )
        rounds = []
        for number, state, published_at in (
            (1, "PUBLISHED", timestamp),
            (2, "SUPERSEDED", timestamp),
            (2, "DRAFT", None),
            (3, "SUPERSEDED", None),
        ):
            rounds.append(
                model("Round").objects.create(
                    draw=draw,
                    number=number,
                    version=2 if state == "DRAFT" else 1,
                    state=state,
                    published_at=published_at,
                    source_fingerprint=str(len(rounds) + 1) * 64,
                )
            )
        match = model("Match").objects.create(
            round=rounds[0],
            number=1,
            code="Saved-M1",
            status="FINAL",
            outcome="PLAYED",
            winner=entries[0],
            side_one_score=2,
            side_two_score=1,
            applied_series_mode="BEST_OF",
            applied_series_length=3,
            started_at=timestamp,
            completed_at=timestamp + timedelta(hours=1),
        )
        for position, entry in enumerate(entries, 1):
            model("MatchSlot").objects.create(
                match=match,
                position=position,
                entry=entry,
                is_resolved=True,
                resolved_entry=entry,
            )
        parent = None
        for state in ("PENDING", "SUPERSEDED"):
            parent = model("TieResolution").objects.create(
                draw=draw,
                method="EXTRA_MATCHES",
                state=state,
                source_fingerprint="e" * 64,
                places=1,
                parent=parent,
            )
            parent.contenders.add(*entries)
        next_stage = model("Stage").objects.create(
            competition=competition,
            sequence=3,
            name="Final",
            format="SINGLE_ELIMINATION",
            series_mode="BEST_OF",
            default_series_length=3,
        )
        next_draw = model("StageDraw").objects.create(
            stage=next_stage,
            version=1,
            source_draw=draw,
            source_fingerprint="f" * 64,
        )
        model("StageEntry").objects.create(
            draw=next_draw, entrant=entries[0].entrant, seed=1, source_entry=entries[0]
        )
        model("ChangeSet").objects.create(
            competition=competition,
            revision=1,
            kind="RESULT_FINALIZED",
            private_data={"old": "private"},
            public_data={"score": [2, 1]},
        )
        names = (
            "Competition",
            "CompetitionEntrant",
            "Stage",
            "StageDraw",
            "StageEntry",
            "Round",
            "Match",
            "MatchSlot",
            "TieResolution",
            "ChangeSet",
        )
        fields = {
            name: [field.attname for field in model(name)._meta.concrete_fields]
            for name in names
        }

        def history():
            return {
                name: list(model(name).objects.order_by("pk").values(*fields[name]))
                for name in names
            }

        before_history = history()
        before_contenders = list(parent.contenders.values_list("pk", flat=True))
        MigrationExecutor(connection).migrate(new_target)
        apps = MigrationExecutor(connection).loader.project_state(new_target).apps
        after_history = history()
        self.assertEqual(after_history, before_history)
        self.assertEqual(
            list(
                model("TieResolution")
                .objects.get(pk=parent.pk)
                .contenders.values_list("pk", flat=True)
            ),
            before_contenders,
        )
        competition = model("Competition").objects.get(pk=competition.pk)
        self.assertIsNone(competition.ended_at)
        self.assertIsNone(competition.ended_stage_id)
        self.assertIsNone(competition.ended_champion_id)
        self.assertEqual(model("Match").objects.get(pk=match.pk).removal_effect, {})
        self.assertFalse(
            model("CompetitionEntrant").objects.exclude(removal_change=None).exists()
        )
        self.assertEqual(
            model("Round").objects.get(pk=source_round.pk).availability_snapshot, {}
        )
        historic = {
            str(entries[0].pk): {
                "entrant_status": "ACTIVE",
                "registration_status": "APPROVED",
                "is_selected": True,
            },
            str(entries[1].pk): {
                "entrant_status": "ACTIVE",
                "registration_status": "APPROVED",
                "is_selected": False,
            },
        }
        current = {
            str(entries[0].pk): {
                "entrant_status": "ACTIVE",
                "registration_status": "APPROVED",
                "is_selected": True,
            },
            str(entries[1].pk): {
                "entrant_status": "WITHDRAWN",
                "registration_status": "REJECTED",
                "is_selected": False,
            },
        }
        for round_ in rounds:
            self.assertEqual(
                model("Round").objects.get(pk=round_.pk).availability_snapshot,
                historic if round_.published_at else current,
            )
