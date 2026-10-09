from django.core.exceptions import ValidationError
from django.test import TestCase

from competitions.commands import (
    configure_elimination,
    create_competition,
    finalize_match,
    publish_draw,
    save_elimination_draw,
    select_entrants,
)
from competitions.models import Match
from competitions.tests.test_commands import CompetitionCommandTests
from competitions.tests.test_round_robin_commands import RoundRobinCommandTests


class QualificationTests(TestCase):
    setUp = CompetitionCommandTests.setUp
    _registration = CompetitionCommandTests._registration
    configure = RoundRobinCommandTests.configure
    setup_stage = RoundRobinCommandTests.setup_stage
    choose = RoundRobinCommandTests.choose
    draw = RoundRobinCommandTests.draw
    publish = RoundRobinCommandTests.publish
    result = RoundRobinCommandTests.result

    def test_all_qualifying_group_still_waits_for_required_play(self):
        from competitions.qualification import stage_qualification

        self.configure(series_mode="BEST_OF", default_series_length=1)
        self.choose(size=2)
        draw = self.draw(group_specs=[("A", 2)])
        self.publish()
        state = stage_qualification(draw)
        self.assertEqual(state["qualification_state"], "PROVISIONAL")
        self.assertEqual(state["cutoffs"], [])
        self.result(
            Match.objects.filter(round__draw=draw).first(),
            side_one_score=1,
            side_two_score=0,
        )
        state = stage_qualification(draw)
        self.assertEqual(state["qualification_state"], "RESOLVED")
        self.assertEqual(
            set(state["qualifier_entry_ids"]),
            set(draw.entries.values_list("pk", flat=True)),
        )

    def _elimination(self):
        from competitions.stage_commands import set_stage_advancement

        self.competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        stage = configure_elimination(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            name="Playoffs",
            format="SINGLE_ELIMINATION",
            default_series_length=1,
        )
        self.competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[self._registration(i + 10).pk for i in range(8)],
        )
        self.competition.refresh_from_db()
        set_stage_advancement(
            actor=self.actor,
            stage_id=stage.pk,
            expected_revision=self.competition.revision,
            advancement_count=3,
        )
        self.competition.refresh_from_db()
        configure_elimination(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            name="Next",
            format="SINGLE_ELIMINATION",
            default_series_length=1,
            stage_sequence=2,
        )
        self.competition.refresh_from_db()
        draw = save_elimination_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            entrant_order=[e.pk for e in entrants],
        )
        self.competition.refresh_from_db()
        publish_draw(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
        )
        for match in Match.objects.filter(round__draw=draw).order_by(
            "round__number", "number"
        ):
            self.competition.refresh_from_db()
            finalize_match(
                actor=self.actor,
                match_id=match.pk,
                expected_revision=self.competition.revision,
                outcome="PLAYED",
                side_one_score=1,
                side_two_score=0,
            )
        self.competition.refresh_from_db()
        return draw

    def test_elimination_top_three_requires_manual_cutoff_choice(self):
        from competitions.qualification import (
            stage_qualification,
            preview_qualification_tie,
            confirm_qualification_tie,
        )

        draw = self._elimination()
        state = stage_qualification(draw)
        self.assertEqual(state["qualification_state"], "AWAITING_RESOLUTION")
        tie = state["cutoffs"][0]
        self.assertEqual((len(tie["entry_ids"]), tie["places"]), (2, 1))
        with self.assertRaises(ValidationError):
            preview_qualification_tie(
                actor=self.actor,
                draw_id=draw.pk,
                expected_revision=self.competition.revision,
                tied_entry_ids=[draw.entries.first().pk],
                method="MANUAL",
                ordered_entry_ids=[draw.entries.first().pk],
            )
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=draw.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=tie["entry_ids"],
            method="MANUAL",
            ordered_entry_ids=tie["entry_ids"],
        )
        with self.assertRaises(ValidationError):
            confirm_qualification_tie(actor=self.actor, token=preview["token"])
        confirm_qualification_tie(
            actor=self.actor, token=preview["token"], internal_reason="Organizer ruling"
        )
        state = stage_qualification(draw)
        self.assertEqual(state["qualification_state"], "RESOLVED")
        self.assertEqual(len(state["qualifier_entry_ids"]), 3)
        self.assertIn(tie["entry_ids"][0], state["qualifier_entry_ids"])
        draw.stage.refresh_from_db()
        self.assertEqual(draw.stage.status, "COMPLETE")

    def test_elimination_extra_match_appends_label_and_keeps_main_champion(self):
        from competitions.qualification import (
            stage_qualification,
            preview_qualification_tie,
            confirm_qualification_tie,
        )

        draw = self._elimination()
        draw.stage.refresh_from_db()
        champion = draw.stage.champion_id
        tie = stage_qualification(draw)["cutoffs"][0]
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=draw.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=tie["entry_ids"],
            method="EXTRA_MATCHES",
        )
        resolution = confirm_qualification_tie(actor=self.actor, token=preview["token"])
        extra = Match.objects.get(round__tie_resolution=resolution)
        self.assertEqual(extra.code, "Playoffs-M8")
        self.competition.refresh_from_db()
        finalize_match(
            actor=self.actor,
            match_id=extra.pk,
            expected_revision=self.competition.revision,
            outcome="PLAYED",
            side_one_score=1,
            side_two_score=0,
        )
        draw.stage.refresh_from_db()
        self.assertEqual(draw.stage.champion_id, champion)
        self.assertEqual(stage_qualification(draw)["qualification_state"], "RESOLVED")
