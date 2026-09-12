from datetime import date
from dataclasses import replace
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from registrations.services import RegistrationMemberInput, _validate_roster


class RosterRoleValidationTests(SimpleTestCase):
    def setUp(self):
        self.game = SimpleNamespace(
            main_roster_size=2,
            substitute_limit=1,
            is_team=True,
            tournament=SimpleNamespace(students_only=False),
        )
        self.members = [
            RegistrationMemberInput(
                first_name_snapshot="Player",
                last_name_snapshot="Example",
                date_of_birth_snapshot=date(2005, 1, 1),
                student_id_snapshot="0012345",
                gamer_tag_snapshot=f"player-{index}",
                school_snapshot="HCMUS",
                is_captain=index == 1,
                display_order=index,
            )
            for index in (1, 2)
        ]

    def validate(self, members):
        _validate_roster(tournament_game=self.game, team_name="Team", members=members)

    def test_missing_main_cannot_be_replaced_with_substitute(self):
        members = [
            replace(member, roster_role=role)
            for member, role in zip(self.members, ("main", "substitute"))
        ]
        with self.assertRaisesMessage(ValidationError, "main"):
            self.validate(members)

    def test_substitute_captain_is_allowed_with_complete_main_roster(self):
        members = [replace(member, is_captain=False) for member in self.members]
        members.append(
            RegistrationMemberInput(
                first_name_snapshot="Player",
                last_name_snapshot="Example",
                date_of_birth_snapshot=date(2005, 1, 1),
                student_id_snapshot="0012345",
                gamer_tag_snapshot="representative",
                school_snapshot="HCMUS",
                is_captain=True,
                display_order=3,
                roster_role="substitute",
            )
        )
        self.validate(members)

    def test_too_many_substitutes_rejected(self):
        members = self.members + [
            RegistrationMemberInput(
                first_name_snapshot="Player",
                last_name_snapshot="Example",
                date_of_birth_snapshot=date(2005, 1, 1),
                student_id_snapshot="0012345",
                gamer_tag_snapshot=f"sub-{index}",
                school_snapshot="HCMUS",
                is_captain=False,
                display_order=index,
                roster_role="substitute",
            )
            for index in (3, 4)
        ]
        with self.assertRaisesMessage(ValidationError, "substitute"):
            self.validate(members)

    def test_unknown_roster_role_rejected(self):
        members = [replace(member, roster_role="unknown") for member in self.members]
        with self.assertRaisesMessage(ValidationError, "role"):
            self.validate(members)
