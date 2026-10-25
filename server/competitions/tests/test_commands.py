from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.tests.factories import create_account
from competitions.commands import (
    apply_correction,
    configure_elimination,
    create_competition,
    finalize_match,
    preview_correction,
    publish_draw,
    save_match_progress,
    save_elimination_draw,
    select_entrants,
    set_match_series_length,
    set_round_series_length,
    start_match,
)
from competitions.models import Competition, Match, Stage
from registrations.models import Registration, RegistrationMember
from tournaments.models import Game, Tournament, TournamentGame


class CompetitionCommandTests(TestCase):
    def test_elimination_setup_rejects_noninteger_and_oversized_lengths(self):
        competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        for length in (True, 3.0, "3", 32769):
            with self.subTest(length=length), self.assertRaises(ValidationError):
                configure_elimination(
                    actor=self.actor,
                    competition_id=competition.pk,
                    expected_revision=competition.revision,
                    format="SINGLE_ELIMINATION",
                    name="Final",
                    default_series_length=length,
                )
        self.assertFalse(competition.stages.exists())

    def setUp(self):
        self.actor = create_account(
            email="admin@example.com",
            password="strong-password",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_superuser=True,
        )
        game = Game.objects.create(name="Chess", slug="chess")
        tournament = Tournament.objects.create(
            name="Cup", slug="cup", is_published=True
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
        self.registrations = [self._registration(index) for index in range(1, 4)]

    def _registration(self, index: int) -> Registration:
        registration = Registration.objects.create(
            tournament_game=self.division,
            status=Registration.Status.APPROVED,
            fee_amount_snapshot="0.00",
            fee_currency_snapshot="VND",
        )
        RegistrationMember.objects.create(
            registration=registration,
            gamer_tag_snapshot=f"Player {index}",
            is_captain=True,
            display_order=1,
        )
        return registration

    def _published_draw(self):
        competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        configure_elimination(
            format="SINGLE_ELIMINATION",
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
        publish_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
        )
        competition.refresh_from_db()
        return competition, draw

    def test_three_entrant_draw_persists_bye_and_advances_to_final(self):
        competition, draw = self._published_draw()

        first_match = draw.rounds.get(number=1).matches.get(number=1)
        semifinal = draw.rounds.get(number=1).matches.get(number=2)
        final = draw.rounds.get(number=2).matches.get(number=1)
        self.assertEqual(first_match.outcome, Match.Outcome.BYE)
        self.assertEqual(first_match.status, Match.Status.FINAL)
        self.assertTrue(final.slots.get(position=1).is_resolved)
        self.assertFalse(final.slots.get(position=2).is_resolved)

        finalize_match(
            actor=self.actor,
            match_id=semifinal.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.PLAYED,
            side_one_score=2,
            side_two_score=0,
        )
        competition.refresh_from_db()
        final.refresh_from_db()
        self.assertTrue(all(slot.is_resolved for slot in final.slots.all()))

        finalize_match(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.PLAYED,
            side_one_score=0,
            side_two_score=2,
        )
        stage = Stage.objects.get(competition=competition)
        self.assertEqual(stage.status, Stage.Status.COMPLETE)
        self.assertIsNotNone(stage.champion_id)

    def test_winner_correction_resets_played_dependant_and_preserves_change(self):
        competition, draw = self._published_draw()
        semifinal = draw.rounds.get(number=1).matches.get(number=2)
        final = draw.rounds.get(number=2).matches.get(number=1)
        finalize_match(
            actor=self.actor,
            match_id=semifinal.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.PLAYED,
            side_one_score=2,
            side_two_score=0,
        )
        competition.refresh_from_db()
        finalize_match(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.PLAYED,
            side_one_score=0,
            side_two_score=2,
        )
        competition.refresh_from_db()

        preview = preview_correction(
            actor=self.actor,
            match_id=semifinal.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.PLAYED,
            side_one_score=0,
            side_two_score=2,
        )
        self.assertEqual(
            [item["match_id"] for item in preview["affected_matches"]], [final.pk]
        )

        apply_correction(
            actor=self.actor,
            token=preview["token"],
            internal_reason="Score entered for the wrong side.",
        )

        final.refresh_from_db()
        competition.refresh_from_db()
        self.assertEqual(final.status, Match.Status.PENDING)
        self.assertIsNone(final.winner_id)
        change = competition.changes.get(revision=competition.revision)
        self.assertEqual(change.kind, "result_corrected")
        self.assertEqual(change.public_data["reset_matches"][0]["match_id"], final.pk)

    def test_series_length_is_frozen_at_start_and_terminal_progress_is_rejected(self):
        competition, draw = self._published_draw()
        match = draw.rounds.get(number=1).matches.get(number=2)
        round_ = match.round

        set_match_series_length(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            series_length=7,
        )
        competition.refresh_from_db()
        set_match_series_length(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            series_length=None,
        )
        competition.refresh_from_db()
        set_round_series_length(
            actor=self.actor,
            round_id=round_.pk,
            expected_revision=competition.revision,
            series_length=5,
        )
        competition.refresh_from_db()
        start_match(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
        )
        competition.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(match.applied_series_length, 5)

        with self.assertRaisesMessage(ValidationError, "reinterpret"):
            set_round_series_length(
                actor=self.actor,
                round_id=round_.pk,
                expected_revision=competition.revision,
                series_length=7,
            )
        with self.assertRaisesMessage(ValidationError, "keeps its applied"):
            set_match_series_length(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=competition.revision,
                series_length=7,
            )

        save_match_progress(
            actor=self.actor,
            match_id=match.pk,
            expected_revision=competition.revision,
            side_one_score=1,
            side_two_score=0,
        )
        competition.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "must be finalized"):
            save_match_progress(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=competition.revision,
                side_one_score=3,
                side_two_score=1,
            )

    def test_forfeit_advances_and_double_forfeit_completes_without_champion(self):
        competition, draw = self._published_draw()
        semifinal = draw.rounds.get(number=1).matches.get(number=2)
        final = draw.rounds.get(number=2).matches.get(number=1)

        finalize_match(
            actor=self.actor,
            match_id=semifinal.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.FORFEIT,
            winner_position=2,
        )
        competition.refresh_from_db()
        final.refresh_from_db()
        self.assertTrue(all(slot.is_resolved for slot in final.slots.all()))

        finalize_match(
            actor=self.actor,
            match_id=final.pk,
            expected_revision=competition.revision,
            outcome=Match.Outcome.DOUBLE_FORFEIT,
        )
        stage = Stage.objects.get(competition=competition)
        self.assertEqual(stage.status, Stage.Status.COMPLETE)
        self.assertTrue(stage.completed_without_champion)
        self.assertIsNone(stage.champion_id)

    def test_publication_rechecks_entrant_approval(self):
        competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        configure_elimination(
            format="SINGLE_ELIMINATION",
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            name="Final bracket",
            default_series_length=1,
        )
        competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            registration_ids=[item.pk for item in self.registrations[:2]],
        )
        competition.refresh_from_db()
        save_elimination_draw(
            actor=self.actor,
            competition_id=competition.pk,
            expected_revision=competition.revision,
            entrant_order=[item.pk for item in entrants],
        )
        competition.refresh_from_db()
        self.registrations[0].status = Registration.Status.REJECTED
        self.registrations[0].save(update_fields=("status",))

        with self.assertRaisesMessage(ValidationError, "must still be approved"):
            publish_draw(
                actor=self.actor,
                competition_id=competition.pk,
                expected_revision=competition.revision,
            )

        self.assertFalse(
            Competition.objects.get(pk=competition.pk).stages.get().published_at
        )
