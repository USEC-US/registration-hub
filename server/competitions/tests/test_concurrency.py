from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.tests.factories import create_account
from competitions.commands import (
    apply_correction,
    configure_single_elimination,
    create_competition,
    finalize_match,
    preview_correction,
    publish_draw,
    save_single_elimination_draw,
    schedule_match,
    select_entrants,
    start_match,
)
from competitions.models import Match, StageDraw
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

    def _saved_draw(self, *, publish=True):
        competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        configure_single_elimination(
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
        draw = save_single_elimination_draw(
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
        self.assertEqual(
            competition.changes.filter(kind="match_finalized").count(), 1
        )

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
        self.assertEqual(
            competition.changes.filter(kind="result_corrected").count(), 1
        )

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
