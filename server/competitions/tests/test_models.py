from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from competitions.models import Competition, Match, MatchSlot, Round, Stage, StageDraw
from tournaments.models import Game, Tournament, TournamentGame


class CompetitionModelTests(TestCase):
    def test_stage_group_plan_and_source_constraints(self):
        from competitions.models import StageGroupPlan

        self.stage.format = Stage.Format.ROUND_ROBIN
        self.stage.save()
        for size, quota in ((1, 1), (2, 0), (2, 3)):
            with self.subTest(size=size, quota=quota):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    StageGroupPlan.objects.create(
                        stage=self.stage,
                        number=1,
                        name="A",
                        size=size,
                        qualifying_places=quota,
                    )
        StageGroupPlan.objects.create(
            stage=self.stage, number=1, name="A", size=3, qualifying_places=2
        )
        source = StageDraw.objects.create(stage=self.stage, version=1)
        for source_id, fingerprint in ((None, "a" * 64), (source.pk, "")):
            with self.assertRaises(IntegrityError), transaction.atomic():
                StageDraw.objects.create(
                    stage=self.stage,
                    version=2,
                    state="SUPERSEDED",
                    source_draw_id=source_id,
                    source_fingerprint=fingerprint,
                )
        with self.assertRaises(IntegrityError), transaction.atomic():
            source.source_draw = source
            source.source_fingerprint = "a" * 64
            source.save()

    def test_display_codes_may_repeat_and_accept_full_unicode_prefix(self):
        draw = StageDraw.objects.create(stage=self.stage, version=1)
        round_ = Round.objects.create(draw=draw, number=1)
        code = "Đ" * 100 + "-M16384"
        first = round_.matches.create(number=1, code=code)
        second = round_.matches.create(number=2, code=code)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(Match.objects.get(pk=second.pk).code, code)

    def setUp(self):
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(name="Cup", slug="cup")
        self.division = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            main_roster_size=1,
            substitute_limit=0,
            registration_opens_at=timezone.now() - timedelta(days=1),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        self.competition = Competition.objects.create(tournament_game=self.division)
        self.stage = Stage.objects.create(
            competition=self.competition,
            sequence=1,
            name="Final bracket",
            format=Stage.Format.SINGLE_ELIMINATION,
            series_mode=Stage.SeriesMode.BEST_OF,
            default_series_length=3,
        )

    def test_competition_protects_owning_division(self):
        with self.assertRaises(ProtectedError):
            self.division.delete()

    def test_match_length_precedence_is_stage_then_round_then_match(self):
        draw = StageDraw.objects.create(stage=self.stage, version=1)
        round_ = Round.objects.create(draw=draw, number=1)
        match = round_.matches.create(number=1, code="M-1")

        self.assertEqual(match.effective_series_length, 3)
        round_.series_length_override = 5
        round_.save(update_fields=("series_length_override",))
        self.assertEqual(match.effective_series_length, 5)
        match.series_length_override = 7
        self.assertEqual(match.effective_series_length, 7)

    def test_double_elimination_requires_a_policy_and_other_formats_forbid_it(self):
        self.assertEqual(self.stage.grand_final_policy, "")
        for sequence, format_, policy in (
            (2, Stage.Format.DOUBLE_ELIMINATION, ""),
            (3, Stage.Format.DOUBLE_ELIMINATION, "UNKNOWN"),
            (4, Stage.Format.SINGLE_ELIMINATION, "RESET"),
        ):
            with self.subTest(format=format_, policy=policy):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Stage.objects.create(
                        competition=self.competition,
                        sequence=sequence,
                        name=f"Stage {sequence}",
                        format=format_,
                        grand_final_policy=policy,
                        series_mode=Stage.SeriesMode.BEST_OF,
                        default_series_length=3,
                    )

        for sequence, policy in ((5, "RESET"), (6, "NO_RESET")):
            stage = Stage.objects.create(
                competition=self.competition,
                sequence=sequence,
                name=f"Stage {sequence}",
                format=Stage.Format.DOUBLE_ELIMINATION,
                grand_final_policy=policy,
                series_mode=Stage.SeriesMode.BEST_OF,
                default_series_length=3,
            )
            self.assertEqual(stage.grand_final_policy, policy)

    def test_match_source_requires_an_outcome_and_empty_slot_forbids_one(self):
        draw = StageDraw.objects.create(stage=self.stage, version=1)
        round_ = Round.objects.create(draw=draw, number=1)
        source = round_.matches.create(number=1, code="SOURCE")

        for number, outcome in ((2, ""), (3, "UNKNOWN")):
            target = round_.matches.create(number=number, code=f"TARGET-{number}")
            with self.subTest(source_outcome=outcome):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    MatchSlot.objects.create(
                        match=target,
                        position=1,
                        source_match=source,
                        source_outcome=outcome,
                    )

        for number, outcome in ((4, MatchSlot.SourceOutcome.WINNER), (5, "LOSER")):
            target = round_.matches.create(number=number, code=f"TARGET-{number}")
            with self.subTest(empty_source_outcome=outcome):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    MatchSlot.objects.create(
                        match=target,
                        position=1,
                        is_empty=True,
                        source_outcome=outcome,
                    )

        target = round_.matches.create(number=6, code="VALID-TARGET")
        for position, outcome in (
            (1, MatchSlot.SourceOutcome.WINNER),
            (2, "LOSER"),
        ):
            slot = MatchSlot.objects.create(
                match=target,
                position=position,
                source_match=source,
                source_outcome=outcome,
            )
            self.assertEqual(slot.source_outcome, outcome)

    def test_double_elimination_sections_and_reserved_match_statuses_exist(self):
        self.assertEqual(Round.Section.UPPER, "UPPER")
        self.assertEqual(Round.Section.LOWER, "LOWER")
        self.assertEqual(Round.Section.FINALS, "FINALS")
        self.assertEqual(Round.Section.NORMAL, "NORMAL")
        self.assertEqual(Match.Status.CONDITIONAL, "CONDITIONAL")
        self.assertEqual(Match.Status.NOT_REQUIRED, "NOT_REQUIRED")


class SwissSchemaTests(TestCase):
    setUp = CompetitionModelTests.setUp

    def test_swiss_settings_and_automatic_group_sizes(self):
        from competitions.models import StageGroupPlan

        self.stage.format = Stage.Format.SWISS_FIXED
        self.stage.advancement_count = 2
        self.stage.swiss_round_count = None
        self.stage.save()
        self.stage.refresh_from_db()
        self.assertIsNone(self.stage.swiss_round_count)
        self.assertIsNone(self.stage.swiss_win_target)
        self.assertIsNone(self.stage.swiss_loss_limit)
        plan = StageGroupPlan.objects.create(
            stage=self.stage, number=1, name="Automatic", size=None, qualifying_places=2
        )
        self.assertIsNone(plan.size)
        for size, quota in ((None, 0), (None, 257), (257, 2)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                StageGroupPlan.objects.filter(pk=plan.pk).update(
                    size=size, qualifying_places=quota
                )
        for field, value in (
            ("swiss_round_count", 0),
            ("swiss_round_count", 65),
            ("swiss_win_target", 0),
            ("swiss_loss_limit", 0),
            ("advancement_count", 1),
            ("advancement_count", 257),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Stage.objects.filter(pk=self.stage.pk).update(**{field: value})
        self.stage.format = Stage.Format.SWISS_THRESHOLD
        self.stage.advancement_count = None
        self.stage.swiss_win_target = 3
        self.stage.swiss_loss_limit = 2
        self.stage.save()
        for values in (
            {"advancement_count": 2},
            {"swiss_round_count": 3},
            {"swiss_win_target": 65},
            {"swiss_loss_limit": 65},
            {"swiss_win_target": 34, "swiss_loss_limit": 32},
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Stage.objects.filter(pk=self.stage.pk).update(**values)
        draw = StageDraw.objects.create(
            stage=self.stage, version=1, swiss_round_limit=4
        )
        self.assertEqual(draw.swiss_round_limit, 4)
        for limit in (0, 65):
            with self.assertRaises(IntegrityError), transaction.atomic():
                StageDraw.objects.filter(pk=draw.pk).update(swiss_round_limit=limit)

    def test_versioned_round_uniqueness_and_publication_constraints(self):
        from competitions.models import StageGroup

        draw = StageDraw.objects.create(stage=self.stage, version=1)
        group = StageGroup.objects.create(
            draw=draw, number=1, name="A", qualifying_places=1
        )
        for scope in (None, group):
            old = Round.objects.create(draw=draw, group=scope, number=1)
            self.assertEqual(
                (
                    old.version,
                    old.state,
                    old.source_fingerprint,
                    old.rematches_authorized,
                    old.published_at,
                ),
                (1, "DRAFT", "", False, None),
            )
            for kwargs in ({"version": 1}, {"version": 2}):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Round.objects.create(draw=draw, group=scope, number=1, **kwargs)
            old.state = "SUPERSEDED"
            old.save(update_fields=("state",))
            replacement = Round.objects.create(
                draw=draw, group=scope, number=1, version=2
            )
            self.assertNotEqual(old.pk, replacement.pk)
            with self.assertRaises(IntegrityError), transaction.atomic():
                Round.objects.create(
                    draw=draw, group=scope, number=1, version=1, state="SUPERSEDED"
                )
        for number, kwargs in enumerate(
            (
                {"version": 0},
                {"state": "PUBLISHED"},
                {"state": "DRAFT", "published_at": timezone.now()},
            ),
            2,
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Round.objects.create(draw=draw, number=number, **kwargs)
        public = Round.objects.create(
            draw=draw, number=5, state="PUBLISHED", published_at=timezone.now()
        )
        public.state = "SUPERSEDED"
        public.save(update_fields=("state",))
        public.refresh_from_db()
        self.assertIsNotNone(public.published_at)


class RoundLifecycleTests(TestCase):
    from competitions.tests import test_commands as _commands
    from competitions.tests import test_round_robin_commands as _round_robin

    setUp = _commands.CompetitionCommandTests.setUp
    _registration = _commands.CompetitionCommandTests._registration
    _published_draw = _commands.CompetitionCommandTests._published_draw
    configure = _round_robin.RoundRobinCommandTests.configure
    setup_stage = _round_robin.RoundRobinCommandTests.setup_stage
    choose = _round_robin.RoundRobinCommandTests.choose
    draw = _round_robin.RoundRobinCommandTests.draw

    def test_publication_and_handoff_retirement_preserve_timestamp(self):
        from competitions.handoff_commands import apply_handoff_impact

        _, draw = self._published_draw()
        draw.refresh_from_db()
        self.assertEqual(
            set(draw.rounds.values_list("state", flat=True)), {"PUBLISHED"}
        )
        self.assertEqual(
            set(draw.rounds.values_list("published_at", flat=True)), {draw.published_at}
        )
        self.assertTrue(draw.rounds.filter(matches__outcome="BYE").exists())
        apply_handoff_impact(
            {
                "retained_draws": [],
                "superseded_draw_ids": [draw.pk],
                "retired_draws": [{"stage_id": draw.stage_id, "was_published": True}],
            }
        )
        self.assertEqual(
            set(draw.rounds.values_list("state", flat=True)), {"SUPERSEDED"}
        )
        self.assertEqual(
            set(draw.rounds.values_list("published_at", flat=True)), {draw.published_at}
        )

    def test_replacing_private_draw_retires_its_rounds(self):
        self.configure()
        self.choose()
        old = self.draw()
        old_round_ids = list(old.rounds.values_list("pk", flat=True))
        new = self.draw()
        self.assertEqual(
            set(old.rounds.values_list("state", flat=True)), {"SUPERSEDED"}
        )
        self.assertEqual(list(old.rounds.values_list("pk", flat=True)), old_round_ids)
        self.assertFalse(old.rounds.filter(published_at__isnull=False).exists())
        self.assertEqual(set(new.rounds.values_list("state", flat=True)), {"DRAFT"})


class CompetitionLifecycleSchemaTests(TestCase):
    setUp = CompetitionModelTests.setUp

    def entrant(self):
        from competitions.models import CompetitionEntrant
        from registrations.models import Registration

        registration = Registration.objects.create(
            tournament_game=self.division,
            status="APPROVED",
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        return CompetitionEntrant.objects.create(
            competition=self.competition,
            registration=registration,
            display_name="Champion",
        )

    def test_ending_timestamp_and_source_stage_must_be_paired(self):
        for values in (
            {"ended_at": timezone.now()},
            {"ended_stage": self.stage},
        ):
            with self.subTest(values=values):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Competition.objects.filter(pk=self.competition.pk).update(**values)
        Competition.objects.filter(pk=self.competition.pk).update(
            ended_at=timezone.now(), ended_stage=self.stage
        )
        self.competition.refresh_from_db()
        self.assertIsNone(self.competition.ended_champion_id)

    def test_champion_requires_an_ending_and_ending_references_are_protected(self):
        entrant = self.entrant()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Competition.objects.filter(pk=self.competition.pk).update(
                ended_champion=entrant
            )
        Competition.objects.filter(pk=self.competition.pk).update(
            ended_at=timezone.now(), ended_stage=self.stage, ended_champion=entrant
        )
        for referenced in (self.stage, entrant):
            with self.subTest(referenced=referenced), self.assertRaises(ProtectedError):
                referenced.delete()

    def test_removal_provenance_defaults_private_and_protects_original_change(self):
        from competitions.models import ChangeSet

        entrant = self.entrant()
        draw = StageDraw.objects.create(stage=self.stage, version=1)
        round_ = Round.objects.create(draw=draw, number=1)
        match = round_.matches.create(number=1, code="M1")
        self.assertIsNone(entrant.removal_change_id)
        self.assertEqual(match.removal_effect, {})
        self.assertEqual(round_.availability_snapshot, {})
        for model, field in (
            (type(entrant), "removal_change"),
            (Match, "removal_effect"),
            (Round, "availability_snapshot"),
        ):
            self.assertFalse(model._meta.get_field(field).editable)
        change = ChangeSet.objects.create(
            competition=self.competition, revision=1, kind="ENTRANT_TRANSITION"
        )
        entrant.removal_change = change
        entrant.save(update_fields=("removal_change",))
        with self.assertRaises(ProtectedError):
            change.delete()
