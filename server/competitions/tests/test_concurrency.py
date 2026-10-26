from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from time import monotonic, sleep

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
from competitions import lifecycle_commands as lifecycle
from competitions.models import Match, Stage, StageDraw, StageEntry
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


class StageHandoffConcurrencyTests(TransactionTestCase):
    setUp = CompetitionConcurrencyTests.setUp
    _registration = CompetitionConcurrencyTests._registration
    _race = CompetitionConcurrencyTests._race

    def _completed_source(self):
        from competitions.tests import test_handoffs as fixtures

        self._chain = fixtures.HandoffTests._chain.__get__(self)
        self._finish = fixtures.HandoffTests._finish.__get__(self)
        source, destination = self._chain()
        self._finish(source)
        return source, destination

    def test_simultaneous_generation_saves_one_draw_and_one_history(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.tests import test_handoffs as fixtures

        self._chain = fixtures.HandoffTests._chain.__get__(self)
        self._finish = fixtures.HandoffTests._finish.__get__(self)
        source, destination = self._chain()
        self._finish(source)
        revision = self.competition.revision
        results = self._race(
            *(
                lambda: generate_next_stage_draw(
                    actor=self.actor,
                    stage_id=destination.pk,
                    expected_revision=revision,
                )
                for _ in range(2)
            )
        )
        self.assertEqual(sorted(results), ["denied", "ok"])
        self.assertEqual(destination.draws.exclude(state="SUPERSEDED").count(), 1)
        self.assertEqual(
            self.competition.changes.filter(kind="successor_draw_saved").count(), 1
        )

    def test_successor_publication_and_source_correction_share_one_revision(self):
        from competitions.handoff_commands import generate_next_stage_draw

        source, destination = self._completed_source()
        draw = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.competition.refresh_from_db()
        revision = self.competition.revision
        match = Match.objects.filter(round__draw=source).order_by("pk").first()
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=1,
        )
        results = self._race(
            lambda: publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                stage_id=destination.pk,
                expected_revision=revision,
            ),
            lambda: apply_correction(
                actor=self.actor,
                token=preview["token"],
                internal_reason="Correction race",
            ),
        )
        self.assertEqual(sorted(results), ["denied", "ok"])
        draw.refresh_from_db()
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.revision, revision + 1)
        self.assertEqual(
            draw.state, "PUBLISHED" if results[0] == "ok" else "SUPERSEDED"
        )

    def test_eligibility_change_serializes_with_generation_and_blocks_publication(self):
        from competitions.handoff_commands import generate_next_stage_draw

        source, destination = self._completed_source()
        registration = source.entries.first().entrant.registration
        revision = self.competition.revision

        def change_eligibility():
            with transaction.atomic():
                TournamentGame.objects.select_for_update().get(pk=self.division.pk)
                Registration.objects.filter(pk=registration.pk).update(
                    status="REJECTED"
                )

        results = self._race(
            lambda: generate_next_stage_draw(
                actor=self.actor, stage_id=destination.pk, expected_revision=revision
            ),
            change_eligibility,
        )
        self.assertEqual(results[1], "ok")
        self.assertEqual(destination.draws.count(), int(results[0] == "ok"))
        self.assertEqual(
            self.competition.changes.filter(kind="successor_draw_saved").count(),
            int(results[0] == "ok"),
        )
        self.competition.refresh_from_db()
        with self.assertRaises(ValidationError):
            publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                stage_id=destination.pk,
                expected_revision=self.competition.revision,
            )


class SwissConcurrencyTests(TransactionTestCase):
    setUp = CompetitionConcurrencyTests.setUp
    _registration = CompetitionConcurrencyTests._registration
    _race = CompetitionConcurrencyTests._race

    def _swiss_round(self):
        from competitions.tests import test_swiss_commands as fixtures

        for name in (
            "_competition",
            "_swiss",
            "_elimination",
            "_revision",
            "_draw",
            "_finish",
        ):
            setattr(self, name, getattr(fixtures.SwissCommandTests, name).__get__(self))
        self.draw = self._draw(5)
        self._finish(self.draw.rounds.get())
        return self.draw

    def test_concurrent_swiss_generation_saves_one_current_round(self):
        from competitions.swiss_commands import generate_swiss_round

        draw = self._swiss_round()
        revision = self._revision()
        original_seed_match_ids = list(
            draw.rounds.get().matches.values_list("pk", flat=True)
        )
        results = self._race(
            *(
                lambda: generate_swiss_round(
                    actor=self.actor, stage_id=self.stage.pk, expected_revision=revision
                )
                for _ in range(2)
            )
        )
        self.assertEqual(sorted(results), ["denied", "ok"])
        self.competition.refresh_from_db()
        self.assertEqual(draw.rounds.filter(state="DRAFT", number=2).count(), 1)
        self.assertEqual(self.competition.revision, revision + 1)
        self.assertEqual(
            self.competition.changes.filter(kind="swiss_round_saved").count(), 1
        )
        self.assertEqual(
            list(draw.rounds.get(number=1).matches.values_list("pk", flat=True)),
            original_seed_match_ids,
        )

    def test_swiss_publication_and_correction_have_one_coherent_revision(self):
        from competitions.swiss_commands import (
            generate_swiss_round,
            publish_swiss_round,
        )

        draw = self._swiss_round()
        pending = generate_swiss_round(
            actor=self.actor, stage_id=self.stage.pk, expected_revision=self._revision()
        )
        revision = self._revision()
        match = draw.rounds.get(number=1).matches.filter(outcome="PLAYED").first()
        preview = preview_correction(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=revision,
            outcome="PLAYED",
            side_one_score=0,
            side_two_score=2,
        )
        results = self._race(
            lambda: publish_swiss_round(
                actor=self.actor, round_id=pending.pk, expected_revision=revision
            ),
            lambda: apply_correction(
                actor=self.actor,
                token=preview["token"],
                internal_reason="Swiss race correction",
            ),
        )
        self.assertEqual(sorted(results), ["denied", "ok"])
        pending.refresh_from_db()
        self.competition.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(self.competition.revision, revision + 1)
        self.assertEqual(
            pending.state, "PUBLISHED" if results[0] == "ok" else "SUPERSEDED"
        )
        self.assertEqual(
            (match.side_one_score, match.side_two_score),
            (2, 0) if results[0] == "ok" else (0, 2),
        )
        self.assertEqual(
            self.competition.changes.filter(revision=revision + 1).count(), 1
        )


class LifecycleConcurrencyTests(TransactionTestCase):
    setUp = CompetitionConcurrencyTests.setUp
    _registration = CompetitionConcurrencyTests._registration
    _saved_draw = CompetitionConcurrencyTests._saved_draw
    _race = CompetitionConcurrencyTests._race
    _swiss_round = SwissConcurrencyTests._swiss_round

    def _ordered_race(self, first, second):
        """Hold the first transaction until PostgreSQL proves the second waits."""
        ready, connected = Event(), Event()
        waiter = []

        def holder():
            with transaction.atomic():
                first()
                ready.set()
                self.assertTrue(connected.wait(timeout=10))
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT cardinality(pg_blocking_pids(%s))", waiter
                        )
                        if cursor.fetchone()[0]:
                            return
                    sleep(0.01)
                self.fail("Second connection never waited on the first transaction")

        def blocked():
            self.assertTrue(ready.wait(timeout=10))
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                waiter.append(cursor.fetchone()[0])
            connected.set()
            second()

        return self._race(holder, blocked)

    def _transition(self, competition, entrant, status):
        competition.refresh_from_db()
        return lifecycle.preview_entrant_transition(
            actor=self.actor,
            entrant_id=entrant.pk,
            expected_revision=competition.revision,
            status=status,
        )

    def _apply(self, preview):
        return lifecycle.apply_entrant_transition(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Race proof",
            confirm_live_forfeits=True,
            confirm_resets=True,
        )

    def _one_revision(self, competition, revision, results):
        self.assertEqual(sorted(results), ["denied", "ok"])
        competition.refresh_from_db()
        self.assertEqual(competition.revision, revision + 1)
        self.assertEqual(competition.changes.filter(revision=revision + 1).count(), 1)
        response = self.client.get(
            f"/api/tournament-games/{self.division.pk}/competition/"
        )
        self.assertEqual(response.status_code, 200)
        public = response.json()
        self.assertEqual(public["competition_revision"], competition.revision)
        self.assertEqual(public["ending"] is not None, competition.ended_at is not None)
        statuses = dict(
            StageEntry.objects.filter(draw__stage__competition=competition).values_list(
                "pk", "entrant__status"
            )
        )
        for stage in public["stages"]:
            for entry in stage["entries"]:
                self.assertEqual(entry["status"], statuses[entry["id"]])
            for round_ in stage["rounds"]:
                for match in round_["matches"]:
                    stored = Match.objects.get(pk=match["id"])
                    for field in (
                        "status",
                        "outcome",
                        "side_one_score",
                        "side_two_score",
                    ):
                        self.assertEqual(match[field], getattr(stored, field))
        self.assertNotIn("Race proof", response.content.decode())
        self.assertEqual(
            list(
                competition.changes.order_by("revision").values_list(
                    "revision", flat=True
                )
            ),
            list(range(1, competition.revision + 1)),
        )

    def test_score_versus_removal_preserves_winning_result_and_history(self):
        competition, draw = self._saved_draw()
        match = Match.objects.get(round__draw=draw)
        entrant = draw.entries.order_by("seed").first().entrant
        preview = self._transition(competition, entrant, "WITHDRAWN")
        revision = competition.revision
        results = self._race(
            lambda: finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=revision,
                outcome="PLAYED",
                side_one_score=2,
                side_two_score=0,
            ),
            lambda: self._apply(preview),
        )
        self._one_revision(competition, revision, results)
        match.refresh_from_db()
        entrant.refresh_from_db()
        self.assertEqual(
            entrant.status, "ACTIVE" if results[0] == "ok" else "WITHDRAWN"
        )
        self.assertEqual(match.outcome, "PLAYED" if results[0] == "ok" else "FORFEIT")
        self.assertEqual(match.status, "FINAL")

    def test_two_restores_undo_authoritative_forfeit_once(self):
        competition, draw = self._saved_draw()
        entrant = draw.entries.order_by("seed").first().entrant
        self._apply(self._transition(competition, entrant, "WITHDRAWN"))
        entrant.refresh_from_db()
        preview = self._transition(competition, entrant, "ACTIVE")
        revision = competition.revision
        results = self._race(lambda: self._apply(preview), lambda: self._apply(preview))
        self._one_revision(competition, revision, results)
        entrant.refresh_from_db()
        self.assertEqual(entrant.status, "ACTIVE")
        self.assertIsNone(entrant.removal_change_id)
        match = Match.objects.get(round__draw=draw)
        self.assertEqual(match.status, "PENDING")
        self.assertIsNone(match.winner_id)

    def test_next_round_publication_versus_removal_has_no_mixed_round(self):
        from competitions.swiss_commands import (
            generate_swiss_round,
            publish_swiss_round,
        )

        draw = self._swiss_round()
        pending = generate_swiss_round(
            actor=self.actor, stage_id=self.stage.pk, expected_revision=self._revision()
        )
        history = list(draw.rounds.get(number=1).matches.order_by("pk").values())
        entrant = draw.entries.order_by("seed").first().entrant
        preview = self._transition(self.competition, entrant, "WITHDRAWN")
        revision = self.competition.revision
        results = self._race(
            lambda: publish_swiss_round(
                actor=self.actor, round_id=pending.pk, expected_revision=revision
            ),
            lambda: self._apply(preview),
        )
        self._one_revision(self.competition, revision, results)
        pending.refresh_from_db()
        entrant.refresh_from_db()
        self.assertEqual(
            pending.state, "PUBLISHED" if results[0] == "ok" else "SUPERSEDED"
        )
        self.assertEqual(
            entrant.status, "ACTIVE" if results[0] == "ok" else "WITHDRAWN"
        )
        self.assertEqual(
            history, list(draw.rounds.get(number=1).matches.order_by("pk").values())
        )

    def _blocked_chain(self, *, complete=False):
        from competitions.tests.test_handoffs import HandoffTests

        self._chain = HandoffTests._chain.__get__(self)
        self._finish = HandoffTests._finish.__get__(self)
        source, destination = self._chain()
        if complete:
            from competitions.handoff_commands import generate_next_stage_draw

            self._finish(source)
            self.retired_draw = generate_next_stage_draw(
                actor=self.actor,
                stage_id=destination.pk,
                expected_revision=self.competition.revision,
            )
        entrant = source.entries.order_by("seed").first().entrant
        self._apply(self._transition(self.competition, entrant, "WITHDRAWN"))
        self.competition.refresh_from_db()
        preview = lifecycle.preview_competition_end(
            actor=self.actor,
            stage_id=source.stage_id,
            expected_revision=self.competition.revision,
        )
        return source, destination, preview

    def _end(self, preview):
        return lifecycle.apply_competition_end(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Locked field cannot continue",
            confirm_resets=True,
        )

    def test_end_versus_score_has_one_winning_revision(self):
        source, _, preview = self._blocked_chain()
        match = source.rounds.first().matches.filter(status="PENDING").first()
        self.assertIsNotNone(match)
        revision = self.competition.revision
        results = self._race(
            lambda: self._end(preview),
            lambda: finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=revision,
                outcome="PLAYED",
                side_one_score=1,
                side_two_score=0,
            ),
        )
        self._one_revision(self.competition, revision, results)
        match.refresh_from_db()
        self.assertEqual(bool(self.competition.ended_at), results[0] == "ok")
        self.assertEqual(match.status, "PENDING" if results[0] == "ok" else "FINAL")

    def test_end_versus_publication_never_exposes_invalid_suffix(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.tests.test_handoffs import HandoffTests

        self._chain = HandoffTests._chain.__get__(self)
        self._finish = HandoffTests._finish.__get__(self)
        source, destination = self._chain()
        self._finish(source)
        suffix = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        registration = source.entries.first().entrant.registration
        Registration.objects.filter(pk=registration.pk).update(status="REJECTED")
        self.competition.refresh_from_db()
        revision = self.competition.revision
        preview = lifecycle.preview_competition_end(
            actor=self.actor, stage_id=source.stage_id, expected_revision=revision
        )
        results = self._race(
            lambda: self._end(preview),
            lambda: publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                stage_id=destination.pk,
                expected_revision=revision,
            ),
        )
        self._one_revision(self.competition, revision, results)
        self.assertEqual(results, ["ok", "denied"])
        suffix.refresh_from_db()
        self.assertEqual(suffix.state, "SUPERSEDED")
        self.assertIsNone(suffix.published_at)

    def test_duplicate_reopen_keeps_retired_history_and_reopens_once(self):
        source, _, preview = self._blocked_chain(complete=True)
        self._end(preview)
        self.competition.refresh_from_db()
        revision = self.competition.revision
        self.retired_draw.refresh_from_db()
        self.assertEqual(self.retired_draw.state, "SUPERSEDED")
        history = list(Match.objects.order_by("pk").values())
        preview = lifecycle.preview_competition_reopen(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=revision,
        )

        def reopen():
            lifecycle.apply_competition_reopen(
                actor=self.actor,
                token=preview["token"],
                internal_reason="Resume",
                confirm_resets=True,
            )

        results = self._race(reopen, reopen)
        self._one_revision(self.competition, revision, results)
        self.assertIsNone(self.competition.ended_at)
        self.retired_draw.refresh_from_db()
        self.assertEqual(self.retired_draw.state, "SUPERSEDED")
        self.assertEqual(history, list(Match.objects.order_by("pk").values()))

    def test_registration_approval_versus_restore_serializes_eligibility(self):
        competition, draw = self._saved_draw()
        entrant = draw.entries.order_by("seed").first().entrant
        self._apply(self._transition(competition, entrant, "WITHDRAWN"))
        entrant.refresh_from_db()
        preview = self._transition(competition, entrant, "ACTIVE")
        revision = competition.revision
        Registration.objects.filter(pk=entrant.registration_id).update(
            status="UNDER_REVIEW"
        )
        results = self._ordered_race(
            lambda: approve_registration(
                actor=self.actor,
                registration_id=entrant.registration_id,
            ),
            lambda: self._apply(preview),
        )
        competition.refresh_from_db()
        entrant.refresh_from_db()
        entrant.registration.refresh_from_db()
        self.assertEqual(results, ["ok", "ok"])
        self.assertEqual(entrant.registration.status, "APPROVED")
        self.assertEqual(
            entrant.status, "ACTIVE" if results[1] == "ok" else "WITHDRAWN"
        )
        self.assertEqual(competition.revision, revision + int(results[1] == "ok"))
        self.assertEqual(
            competition.changes.filter(revision__gt=revision).count(),
            int(results[1] == "ok"),
        )

    def test_registration_approval_waits_before_swiss_publication(self):
        from competitions.swiss_commands import (
            generate_swiss_round,
            publish_swiss_round,
        )

        draw = self._swiss_round()
        pending = generate_swiss_round(
            actor=self.actor, stage_id=self.stage.pk, expected_revision=self._revision()
        )
        revision = self._revision()
        registration = draw.entries.first().entrant.registration
        Registration.objects.filter(pk=registration.pk).update(status="UNDER_REVIEW")
        results = self._ordered_race(
            lambda: approve_registration(
                actor=self.actor, registration_id=registration.pk
            ),
            lambda: publish_swiss_round(
                actor=self.actor, round_id=pending.pk, expected_revision=revision
            ),
        )
        self.assertEqual(results, ["ok", "ok"])
        self.competition.refresh_from_db()
        pending.refresh_from_db()
        registration.refresh_from_db()
        self.assertEqual(registration.status, "APPROVED")
        self.assertEqual(pending.state, "PUBLISHED")
        self.assertEqual(self.competition.revision, revision + 1)
        self.assertEqual(
            self.competition.changes.filter(revision=revision + 1).count(), 1
        )
