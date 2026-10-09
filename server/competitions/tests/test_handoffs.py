from itertools import product
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from competitions.commands import (
    configure_elimination,
    create_competition,
    finalize_match,
    publish_draw,
    save_elimination_draw,
    select_entrants,
)
from competitions.models import Match, StageDraw
from competitions.round_robin_commands import (
    configure_round_robin,
    save_round_robin_draw,
)
from competitions.tests import test_commands as fixtures


class HandoffTests(TestCase):
    setUp = fixtures.CompetitionCommandTests.setUp
    _registration = fixtures.CompetitionCommandTests._registration

    def _chain(
        self,
        source_format="SINGLE_ELIMINATION",
        destination_format="SINGLE_ELIMINATION",
        size=4,
        formats=None,
        advance_count=None,
        publish=True,
    ):
        from competitions.stage_commands import set_stage_advancement, set_stage_groups

        self.competition = create_competition(
            actor=self.actor, tournament_game_id=self.division.pk
        )
        stages = []
        formats = formats or (source_format, destination_format)
        incoming = size
        for sequence, format_ in enumerate(formats, 1):
            self.competition.refresh_from_db()
            kwargs = dict(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
                name=f"Stage{sequence}",
                default_series_length=1,
                stage_sequence=sequence,
            )
            if format_ == "ROUND_ROBIN":
                stage = configure_round_robin(
                    **kwargs,
                    meetings=1,
                    series_mode="BEST_OF",
                    win_points=3,
                    draw_points=1,
                    loss_points=0,
                )
                self.competition.refresh_from_db()
                set_stage_groups(
                    actor=self.actor,
                    stage_id=stage.pk,
                    expected_revision=self.competition.revision,
                    group_specs=[
                        (
                            "A",
                            incoming,
                            (advance_count or incoming)
                            if sequence < len(formats)
                            else incoming,
                        )
                    ],
                )
            else:
                stage = configure_elimination(
                    **kwargs,
                    format=format_,
                    grand_final_policy="RESET"
                    if format_ == "DOUBLE_ELIMINATION"
                    else "",
                )
                if sequence < len(formats):
                    self.competition.refresh_from_db()
                    set_stage_advancement(
                        actor=self.actor,
                        stage_id=stage.pk,
                        expected_revision=self.competition.revision,
                        advancement_count=advance_count or incoming,
                    )
            stages.append(stage)
            if sequence < len(formats):
                incoming = advance_count or incoming
        self.competition.refresh_from_db()
        entrants = select_entrants(
            actor=self.actor,
            competition_id=self.competition.pk,
            expected_revision=self.competition.revision,
            registration_ids=[self._registration(i + 10).pk for i in range(size)],
        )
        self.competition.refresh_from_db()
        if source_format == "ROUND_ROBIN":
            draw = save_round_robin_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
                group_specs=[("A", stages[0].group_plans.get().qualifying_places)],
                ordered_entrant_ids=[e.pk for e in entrants],
            )
        else:
            draw = save_elimination_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
                entrant_order=[e.pk for e in entrants],
            )
        self.competition.refresh_from_db()
        if publish:
            publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                expected_revision=self.competition.revision,
            )
        self.competition.refresh_from_db()
        return draw, stages[1]

    def _finish(self, draw):
        while True:
            match = (
                Match.objects.filter(round__draw=draw, status="PENDING")
                .order_by("pk")
                .first()
            )
            if match is None:
                break
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

    def test_all_nine_combinations_save_exact_random_positions_and_source_links(self):
        from competitions.handoff_commands import generate_next_stage_draw

        for source_format, destination_format in product(
            ("ROUND_ROBIN", "SINGLE_ELIMINATION", "DOUBLE_ELIMINATION"), repeat=2
        ):
            with (
                self.subTest(source=source_format, destination=destination_format),
                transaction.atomic(),
            ):
                source, destination = self._chain(source_format, destination_format)
                self._finish(source)
                source_ids = list(
                    source.entries.order_by("pk").values_list("pk", flat=True)
                )
                with patch(
                    "competitions.handoff_commands.secrets.SystemRandom"
                ) as random:
                    random.return_value.shuffle.side_effect = lambda values: (
                        values.reverse()
                    )
                    draw = generate_next_stage_draw(
                        actor=self.actor,
                        stage_id=destination.pk,
                        expected_revision=self.competition.revision,
                    )
                self.assertEqual(draw.source_draw_id, source.pk)
                self.assertEqual(len(draw.source_fingerprint), 64)
                self.assertEqual(
                    list(draw.entries.values_list("source_entry_id", flat=True)),
                    list(reversed(source_ids)),
                )
                self.assertEqual(
                    set(draw.entries.values_list("entrant_id", flat=True)),
                    set(source.entries.values_list("entrant_id", flat=True)),
                )
                self.competition.refresh_from_db()
                publish_draw(
                    actor=self.actor,
                    competition_id=self.competition.pk,
                    stage_id=destination.pk,
                    expected_revision=self.competition.revision,
                )
                self.assertEqual(
                    StageDraw.objects.filter(
                        stage=destination, state="PUBLISHED"
                    ).count(),
                    1,
                )
                transaction.set_rollback(True)

    def test_pending_play_direct_bypass_repeated_revision_and_eligibility(self):
        from competitions.handoff_commands import generate_next_stage_draw

        source, destination = self._chain("ROUND_ROBIN")
        with self.assertRaises(ValidationError):
            generate_next_stage_draw(
                actor=self.actor,
                stage_id=destination.pk,
                expected_revision=self.competition.revision,
            )
        with self.assertRaises(ValidationError):
            save_elimination_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                stage_id=destination.pk,
                expected_revision=self.competition.revision,
                randomize=True,
            )
        self._finish(source)
        revision = self.competition.revision
        draw = generate_next_stage_draw(
            actor=self.actor, stage_id=destination.pk, expected_revision=revision
        )
        with self.assertRaises(ValidationError):
            generate_next_stage_draw(
                actor=self.actor, stage_id=destination.pk, expected_revision=revision
            )
        self.competition.refresh_from_db()
        self.assertEqual(
            generate_next_stage_draw(
                actor=self.actor,
                stage_id=destination.pk,
                expected_revision=self.competition.revision,
            ).pk,
            draw.pk,
        )
        registration = source.entries.first().entrant.registration
        registration.status = "REJECTED"
        registration.save()
        with self.assertRaises(ValidationError):
            publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                stage_id=destination.pk,
                expected_revision=self.competition.revision,
            )

    def test_top_three_manual_choice_feeds_exact_round_robin_field(self):
        from competitions.handoff_commands import generate_next_stage_draw
        from competitions.qualification import (
            stage_qualification,
            preview_qualification_tie,
            confirm_qualification_tie,
        )

        source, destination = self._chain(
            destination_format="ROUND_ROBIN", advance_count=3
        )
        self._finish(source)
        state = stage_qualification(source)
        self.assertEqual(state["qualification_state"], "AWAITING_RESOLUTION")
        tie = state["cutoffs"][0]
        preview = preview_qualification_tie(
            actor=self.actor,
            draw_id=source.pk,
            expected_revision=self.competition.revision,
            tied_entry_ids=tie["entry_ids"],
            method="MANUAL",
            ordered_entry_ids=tie["entry_ids"],
        )
        confirm_qualification_tie(
            actor=self.actor, token=preview["token"], internal_reason="Top three cutoff"
        )
        self.competition.refresh_from_db()
        draw = generate_next_stage_draw(
            actor=self.actor,
            stage_id=destination.pk,
            expected_revision=self.competition.revision,
        )
        self.assertEqual(draw.entries.count(), 3)
        self.assertEqual(
            set(draw.entries.values_list("source_entry_id", flat=True)),
            set(stage_qualification(source)["qualifier_entry_ids"]),
        )
        self.assertEqual(draw.groups.get().entries.count(), 3)

    def test_three_stage_chain_waits_for_each_source_and_restarts_labels(self):
        from competitions.handoff_commands import generate_next_stage_draw

        source, second = self._chain(
            formats=("SINGLE_ELIMINATION", "ROUND_ROBIN", "DOUBLE_ELIMINATION")
        )
        third = self.competition.stages.get(sequence=3)
        self.assertFalse(second.draws.exists())
        self.assertFalse(third.draws.exists())
        with self.assertRaises(ValidationError):
            generate_next_stage_draw(
                actor=self.actor,
                stage_id=third.pk,
                expected_revision=self.competition.revision,
            )
        draws = [source]
        for stage in (second, third):
            self._finish(draws[-1])
            draw = generate_next_stage_draw(
                actor=self.actor,
                stage_id=stage.pk,
                expected_revision=self.competition.revision,
            )
            before = list(draw.entries.values_list("pk", "seed"))
            self.assertTrue(
                Match.objects.filter(round__draw=draw, code=f"{stage.name}-M1").exists()
            )
            self.assertEqual(list(draw.entries.values_list("pk", "seed")), before)
            self.competition.refresh_from_db()
            publish_draw(
                actor=self.actor,
                competition_id=self.competition.pk,
                stage_id=stage.pk,
                expected_revision=self.competition.revision,
            )
            draws.append(draw)
        self.assertEqual(draws[2].source_draw_id, draws[1].pk)
