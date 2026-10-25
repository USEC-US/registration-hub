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
        self.assertEqual(extra.round.state, "PUBLISHED")
        self.assertIsNotNone(extra.round.published_at)
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

    def test_inconsistent_terminal_exits_report_blocked_qualification(self):
        from competitions.qualification import stage_qualification

        draw = self._elimination()
        semifinals = list(
            Match.objects.filter(round__draw=draw, round__number=1).order_by("pk")
        )
        loser = semifinals[0].slots.get(position=2).resolved_entry_id
        semifinals[1].slots.filter(position=2).update(resolved_entry_id=loser)
        state = stage_qualification(draw)
        self.assertEqual(state["qualification_state"], "BLOCKED")
        self.assertEqual(state["qualifier_entry_ids"], [])
        self.assertIn("terminal", state["block_reason"].lower())


class SwissQualificationTests(TestCase):
    from competitions.tests.test_swiss_commands import (
        SwissCommandTests as command_fixture,
    )

    setUp = command_fixture.setUp
    _registration = command_fixture._registration
    _competition = command_fixture._competition
    _swiss = command_fixture._swiss
    _elimination = command_fixture._elimination
    _revision = command_fixture._revision
    _draw = command_fixture._draw
    _finish = command_fixture._finish
    _generate = command_fixture._generate
    _publish = command_fixture._publish

    def test_fixed_requires_every_published_configured_ordinary_round(self):
        from competitions.qualification import stage_qualification

        draw = self._draw(8, advancement_count=8, round_count=3)
        for number in range(1, 4):
            round_ = draw.rounds.get(number=1) if number == 1 else self._generate()
            if number > 1:
                self._publish(round_)
            self._finish(round_)
            state = stage_qualification(draw)
            draw.stage.refresh_from_db()
            self.assertEqual(
                state["qualification_state"],
                "RESOLVED" if number == 3 else "PROVISIONAL",
            )
            self.assertEqual(
                draw.stage.status, "COMPLETE" if number == 3 else "IN_PROGRESS"
            )
            self.assertIsNone(draw.stage.champion_id)
        self.assertEqual(
            set(state["qualifier_entry_ids"]),
            set(draw.entries.values_list("pk", flat=True)),
        )

    def test_fixed_cutoff_uses_manual_or_extra_match_workflow_without_ordinary_credit(
        self,
    ):
        from competitions.qualification import (
            stage_qualification,
            preview_qualification_tie,
            confirm_qualification_tie,
        )
        from competitions.swiss_commands import swiss_standings
        from django.db import transaction

        for method in ("MANUAL", "EXTRA_MATCHES"):
            with self.subTest(method=method), transaction.atomic():
                draw = self._draw(8, advancement_count=2, round_count=1, tiebreaks=[])
                self._finish(draw.rounds.get())
                state = stage_qualification(draw)
                # The four winners share ordinary points; seeds cannot choose the cutoff.
                self.assertEqual(state["qualification_state"], "AWAITING_RESOLUTION")
                self.assertEqual([len(band) for band in state["bands"]], [4, 4])
                draw.stage.refresh_from_db()
                self.assertEqual(draw.stage.status, "AWAITING")
                self.assertEqual(draw.swiss_round_limit, 1)
                with self.assertRaises(ValidationError):
                    self._generate()
                before = [
                    (r.entry_id, r.wins, r.losses, r.points, r.bye_count)
                    for r in swiss_standings(draw)
                ]
                tie = state["cutoffs"][0]
                preview = preview_qualification_tie(
                    actor=self.actor,
                    draw_id=draw.pk,
                    expected_revision=self._revision(),
                    tied_entry_ids=tie["entry_ids"],
                    method=method,
                    ordered_entry_ids=tie["entry_ids"] if method == "MANUAL" else (),
                )
                resolution = confirm_qualification_tie(
                    actor=self.actor,
                    token=preview["token"],
                    internal_reason="Cutoff ruling",
                )
                if method == "EXTRA_MATCHES":
                    self.assertEqual(
                        stage_qualification(draw)["qualification_state"],
                        "AWAITING_RESOLUTION",
                    )
                    for match in Match.objects.filter(
                        round__tie_resolution=resolution
                    ).order_by("pk"):
                        slots = list(
                            match.slots.select_related("resolved_entry").order_by(
                                "position"
                            )
                        )
                        first_wins = (
                            slots[0].resolved_entry.seed < slots[1].resolved_entry.seed
                        )
                        finalize_match(
                            actor=self.actor,
                            match_id=match.pk,
                            expected_revision=self._revision(),
                            outcome="PLAYED",
                            side_one_score=int(first_wins),
                            side_two_score=int(not first_wins),
                        )
                after = [
                    (r.entry_id, r.wins, r.losses, r.points, r.bye_count)
                    for r in swiss_standings(draw)
                ]
                self.assertEqual(before, after)
                self.assertEqual(
                    stage_qualification(draw)["qualification_state"], "RESOLVED"
                )
                self.assertEqual(
                    len(stage_qualification(draw)["qualifier_entry_ids"]), 2
                )
                draw.stage.refresh_from_db()
                self.assertEqual(draw.stage.status, "COMPLETE")
                self.assertIsNone(draw.stage.champion_id)
                transaction.set_rollback(True)

    def test_threshold_waits_until_no_active_entries_and_advances_actual_qualified_set(
        self,
    ):
        from competitions.qualification import stage_qualification
        from competitions.swiss_commands import swiss_standings

        draw = self._draw(
            9,
            format="SWISS_THRESHOLD",
            advancement_count=None,
            win_target=2,
            loss_limit=2,
        )
        for number in range(1, 4):
            round_ = draw.rounds.get(number=1) if number == 1 else self._generate()
            if number > 1:
                self._publish(round_)
            self._finish(round_)
            rows = swiss_standings(draw)
            active = any(r.status == "ACTIVE" for r in rows)
            state = stage_qualification(draw)
            self.assertEqual(
                state["qualification_state"], "PROVISIONAL" if active else "RESOLVED"
            )
            if not active:
                self.assertEqual(
                    set(state["qualifier_entry_ids"]),
                    {r.entry_id for r in rows if r.status == "QUALIFIED"},
                )
                break
        self.assertFalse(active)
        draw.stage.refresh_from_db()
        self.assertEqual(draw.stage.status, "COMPLETE")
        self.assertIsNone(draw.stage.champion_id)

    def test_private_and_superseded_fixture_results_do_not_enter_qualification_projection(
        self,
    ):
        from competitions.qualification import stage_qualification

        draw = self._draw(8, advancement_count=8, round_count=2)
        self._finish(draw.rounds.get())
        old = self._generate()
        old_matches = list(old.matches.all())
        new = self._generate(regenerate=True)
        private = list(new.matches.all())
        snapshot = stage_qualification(draw)
        Match.objects.filter(pk__in=[m.pk for m in old_matches + private]).update(
            status="FINAL", outcome="DOUBLE_FORFEIT"
        )
        projected = {
            m.pk: {"status": "FINAL", "outcome": "DOUBLE_FORFEIT"}
            for m in old_matches + private
        }
        self.assertEqual(
            stage_qualification(draw, projected_matches=projected), snapshot
        )
        self.assertEqual(snapshot["qualification_state"], "PROVISIONAL")
