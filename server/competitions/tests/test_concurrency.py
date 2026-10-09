from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.tests.factories import create_account
from competitions.commands import (
    apply_correction,
    configure_elimination,
    create_competition,
    finalize_match,
    preview_correction,
    publish_draw,
    save_elimination_draw,
    schedule_match,
    select_entrants,
    start_match,
)
from competitions.models import Match, Stage, StageDraw
from registrations.models import Registration, RegistrationMember
from registrations.services import approve_registration
from tournaments.models import Game, Tournament, TournamentGame


class CompetitionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock races require PostgreSQL")
        self.actor = create_account(
            email="competition-race@example.com",
            password="strong-password",
            first_name="Competition",
            last_name="Race",
            is_staff=True,
            is_superuser=True,
        )
        game = Game.objects.create(name="Chess", slug="race-chess")
        tournament = Tournament.objects.create(
            name="Race Cup", slug="race-cup", is_published=True
        )
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
        self.registrations = [self._registration(index) for index in range(1, 3)]

    def _registration(self, index):
        registration = Registration.objects.create(
            tournament_game=self.division,
            status=Registration.Status.APPROVED,
            fee_amount_snapshot="0.00",
            fee_currency_snapshot="VND",
        )
        RegistrationMember.objects.create(
            registration=registration,
            gamer_tag_snapshot=f"Race Player {index}",
            is_captain=True,
            display_order=1,
        )
        return registration

    def _saved_draw(self, *, publish=True, format="SINGLE_ELIMINATION"):
        competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        configure_elimination(
            format=format,
            grand_final_policy="RESET" if format == "DOUBLE_ELIMINATION" else "",
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            name="Final bracket",
            default_series_length=3,
        )
        competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            registration_ids=[item.pk for item in self.registrations],
        )
        competition.refresh_from_db()
        draw = save_elimination_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            entrant_order=[item.pk for item in entrants],
        )
        competition.refresh_from_db()
        if publish:
            publish_draw(
                actor=self.actor,
                competition_id=competition.pk,
                expected_revision=competition.revision,
            )
            competition.refresh_from_db()
        return competition, draw

    def _race(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                barrier.wait(timeout=10)
                try:
                    operation()
                except ValidationError:
                    return "denied"
                return "ok"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=20) for future in futures]

    def test_simultaneous_finalization_advances_once(self):
        competition, draw = self._saved_draw()
        match = Match.objects.get(round__draw=draw)
        revision = competition.revision

        results = self._race(
            *(
                lambda: finalize_match(
                    actor=self.actor,
                    match_id=match.pk,
                    expected_revision=revision,
                    outcome=Match.Outcome.PLAYED,
                    side_one_score=2,
                    side_two_score=0,
                )
                for _ in range(2)
            )
        )

        match.refresh_from_db()
        self.assertEqual(sorted(results), ["denied", "ok"])
        self.assertEqual(match.status, Match.Status.FINAL)
        self.assertEqual(competition.changes.filter(kind="match_finalized").count(), 1)

    def test_stale_revision_cannot_start_after_schedule_change(self):
        competition, draw = self._saved_draw()
        match = Match.objects.get(round__draw=draw)
        stale_revision = competition.revision
        schedule_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=stale_revision,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        with self.assertRaisesMessage(ValidationError, "Competition changed"):
            start_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=stale_revision,
            )

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.PENDING)
        self.assertIsNone(match.started_at)

    def test_simultaneous_correction_applies_once(self):
        competition, draw = self._saved_draw()
        match = Match.objects.get(round__draw=draw)
        finalize_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.PLAYED,
            side_one_score=2,
            side_two_score=0,
        )
        competition.refresh_from_db()
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.PLAYED,
            side_one_score=0,
            side_two_score=2,
        )

        results = self._race(
            *(
                lambda: apply_correction(
                    actor=self.actor,
                    token=preview["token"],
                    internal_reason="Concurrent correction test.",
                )
                for _ in range(2)
            )
        )

        match.refresh_from_db()
        self.assertEqual(sorted(results), ["denied", "ok"])
        self.assertEqual(match.side_one_score, 0)
        self.assertEqual(match.side_two_score, 2)
        self.assertEqual(competition.changes.filter(kind="result_corrected").count(), 1)

    def test_approval_and_publication_share_the_division_lock(self):
        competition, draw = self._saved_draw(publish=False)
        registration = self.registrations[0]
        Registration.objects.filter(pk=registration.pk).update(
            status=Registration.Status.UNDER_REVIEW
        )
        revision = competition.revision

        results = self._race(
            lambda: approve_registration(
                actor=self.actor, registration_id=registration.pk
            ),
            lambda: publish_draw(
                actor=self.actor,
                competition_id=competition.pk,
                expected_revision=revision,
            ),
        )

        registration.refresh_from_db()
        draw.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.APPROVED)
        self.assertIn(results.count("ok"), (1, 2))
        if draw.state == StageDraw.State.PUBLISHED:
            self.assertEqual(results.count("ok"), 2)
        else:
            self.assertEqual(draw.state, StageDraw.State.DRAFT)
            self.assertEqual(results.count("denied"), 1)

    def test_double_elimination_simultaneous_upper_finalization_routes_both_once(self):
        competition, draw = self._saved_draw(format="DOUBLE_ELIMINATION")
        upper = Match.objects.get(round__draw=draw, round__section="UPPER")
        entries = list(
            upper.slots.order_by("position").values_list("resolved_entry_id", flat=True)
        )
        revision = competition.revision
        results = self._race(
            *(
                lambda: finalize_match(
                    actor=self.actor,
                    match_id=upper.pk,
                    expected_revision=revision,
                    outcome="PLAYED",
                    side_one_score=2,
                    side_two_score=0,
                )
                for _ in range(2)
            )
        )
        self.assertEqual(sorted(results), ["denied", "ok"])
        competition.refresh_from_db()
        self.assertEqual(competition.revision, revision + 1)
        self.assertEqual(competition.changes.filter(kind="match_finalized").count(), 1)
        destinations = list(upper.dependent_slots.order_by("position"))
        self.assertEqual(len(destinations), 2)
        self.assertTrue(all(slot.is_resolved for slot in destinations))
        self.assertEqual([slot.resolved_entry_id for slot in destinations], entries)
        self.assertEqual(
            [slot.source_outcome for slot in destinations], ["WINNER", "LOSER"]
        )

    def test_stale_correction_waiting_for_downstream_final_has_no_partial_reset(self):
        competition, draw = self._saved_draw(format="DOUBLE_ELIMINATION")
        upper = Match.objects.get(round__draw=draw, round__section="UPPER")
        finalize_match(
            actor=self.actor,
            match_id=upper.pk,
            expected_revision=competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        competition.refresh_from_db()
        revision = competition.revision
        preview = preview_correction(
            actor=self.actor,
            match_id=upper.pk,
            expected_revision=revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        final = Match.objects.get(
            round__draw=draw, round__section="FINALS", round__number=1
        )
        finalized, correction_started = Event(), Event()

        def downstream():
            with transaction.atomic():
                finalize_match(
                    actor=self.actor,
                    match_id=final.pk,
                    expected_revision=revision,
                    outcome="PLAYED",
                    side_one_score=0,
                    side_two_score=2,
                )
                finalized.set()
                self.assertTrue(correction_started.wait(timeout=10))

        def stale_correction():
            self.assertTrue(finalized.wait(timeout=10))
            correction_started.set()
            apply_correction(
                actor=self.actor, token=preview["token"], internal_reason="Stale race"
            )

        self.assertEqual(self._race(downstream, stale_correction), ["ok", "denied"])
        competition.refresh_from_db()
        self.assertEqual(competition.revision, revision + 1)
        self.assertEqual(competition.changes.filter(kind="result_corrected").count(), 0)
        self.assertEqual(competition.changes.filter(kind="match_finalized").count(), 2)
        upper.refresh_from_db()
        final.refresh_from_db()
        self.assertEqual((upper.side_one_score, upper.side_two_score), (2, 0))
        self.assertEqual((final.side_one_score, final.side_two_score), (0, 2))
        self.assertEqual(final.status, "FINAL")
        reset = Match.objects.get(
            round__draw=draw, round__section="FINALS", round__number=2
        )
        self.assertEqual(reset.status, "PENDING")
        self.assertEqual(
            list(
                reset.slots.order_by("position").values_list(
                    "resolved_entry_id", flat=True
                )
            ),
            list(
                final.slots.order_by("position").values_list(
                    "resolved_entry_id", flat=True
                )
            ),
        )
        self.assertEqual(Stage.objects.get(pk=draw.stage_id).status, "IN_PROGRESS")


class RoundRobinConcurrencyTests(CompetitionConcurrencyTests):
    def _tied_group(self):
        from competitions.round_robin_commands import (
            configure_round_robin,
            save_round_robin_draw,
            preview_group_tie,
        )

        competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        configure_round_robin(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            name="Groups",
            meetings=1,
            series_mode="FIXED_GAMES",
            default_series_length=2,
            win_points=3,
            draw_points=1,
            loss_points=0,
            tiebreaks=[],
        )
        competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            registration_ids=[r.pk for r in self.registrations],
        )
        competition.refresh_from_db()
        draw = save_round_robin_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            group_specs=[("A", 1)],
            ordered_entrant_ids=[e.pk for e in entrants],
        )
        competition.refresh_from_db()
        publish_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
        )
        competition.refresh_from_db()
        match = Match.objects.get(round__draw=draw)
        finalize_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            outcome="PLAYED",
            side_one_score=1,
            side_two_score=1,
        )
        competition.refresh_from_db()
        ids = list(draw.entries.values_list("pk", flat=True))
        preview = preview_group_tie(
            actor=self.actor,
            group_id=draw.groups.get().pk,
            expected_revision=competition.revision,
            tied_entry_ids=ids,
            method="MANUAL",
            ordered_entry_ids=ids,
        )
        return competition, match, preview

    def test_concurrent_tie_confirmation_records_one_decision(self):
        from competitions.round_robin_commands import confirm_group_tie

        competition, match, preview = self._tied_group()
        revision = competition.revision
        results = self._race(
            *(
                lambda: confirm_group_tie(
                    actor=self.actor,
                    token=preview["token"],
                    internal_reason="Confirmed",
                )
                for _ in range(2)
            )
        )
        self.assertEqual(sorted(results), ["denied", "ok"])
        competition.refresh_from_db()
        self.assertEqual(competition.revision, revision + 1)
        self.assertEqual(
            competition.changes.filter(kind="group_tie_confirmed").count(), 1
        )

    def test_correction_and_tie_confirmation_use_one_revision(self):
        from competitions.round_robin_commands import confirm_group_tie

        competition, match, preview = self._tied_group()
        correction = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            outcome="PLAYED",
            side_one_score=2,
            side_two_score=0,
        )
        results = self._race(
            lambda: confirm_group_tie(
                actor=self.actor, token=preview["token"], internal_reason="Choice"
            ),
            lambda: apply_correction(
                actor=self.actor, token=correction["token"], internal_reason="Typo"
            ),
        )
        self.assertEqual(sorted(results), ["denied", "ok"])
