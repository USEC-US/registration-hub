from datetime import date, timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from registrations.serializers import RegistrationMemberSubmissionSerializer
from registrations.models import Registration
from rest_framework.test import APITestCase
from django.test import override_settings
from . import test_guest_submission


class PlayerDetailsSerializerTests(SimpleTestCase):
    def payload(self):
        return {
            "first_name_snapshot": "  Minh Anh  ",
            "last_name_snapshot": "  Nguyễn  ",
            "date_of_birth_snapshot": "2005-03-12",
            "student_id_snapshot": "  0012345  ",
            "gamer_tag_snapshot": "Player#ONE",
            "institution_label": "HCMUS",
            "is_captain": True,
            "roster_role": "main",
            "display_order": 1,
        }

    def test_names_birth_date_and_student_id_are_validated_without_losing_leading_zeroes(
        self,
    ):
        serializer = RegistrationMemberSubmissionSerializer(data=self.payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["first_name_snapshot"], "Minh Anh")
        self.assertEqual(serializer.validated_data["last_name_snapshot"], "Nguyễn")
        self.assertEqual(
            serializer.validated_data["date_of_birth_snapshot"], date(2005, 3, 12)
        )
        self.assertEqual(serializer.validated_data["student_id_snapshot"], "0012345")

    def test_names_and_birth_date_are_required_for_each_player(self):
        for field in (
            "first_name_snapshot",
            "last_name_snapshot",
            "date_of_birth_snapshot",
        ):
            for missing in (True, False):
                with self.subTest(field=field, missing=missing):
                    payload = self.payload()
                    if missing:
                        payload.pop(field)
                    else:
                        payload[field] = ""
                    serializer = RegistrationMemberSubmissionSerializer(data=payload)
                    self.assertFalse(serializer.is_valid())
                    self.assertIn(field, serializer.errors)

    def test_invalid_and_future_birth_dates_are_rejected(self):
        for value in (
            "2005-02-30",
            "not-a-date",
            (timezone.localdate() + timedelta(days=1)).isoformat(),
        ):
            with self.subTest(value=value):
                payload = self.payload()
                payload["date_of_birth_snapshot"] = value
                serializer = RegistrationMemberSubmissionSerializer(data=payload)
                self.assertFalse(serializer.is_valid())
                self.assertIn("date_of_birth_snapshot", serializer.errors)


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
class PlayerDetailsApiTests(APITestCase):
    setUp = test_guest_submission.GuestSubmissionTests.setUp
    _create_registration = (
        test_guest_submission.GuestSubmissionTests._create_registration
    )
    payload = test_guest_submission.GuestSubmissionTests.payload
    post = test_guest_submission.GuestSubmissionTests.post
    team_payload = test_guest_submission.GuestSubmissionTests.team_payload

    def test_details_are_saved_for_main_players_and_substitutes_but_not_returned_in_receipt(
        self,
    ):
        payload = self.team_payload()
        for index, member in enumerate(payload["members"]):
            member.update(
                first_name_snapshot=f" Given {index} ",
                last_name_snapshot=" Nguyễn ",
                student_id_snapshot=f" 00{index} ",
                date_of_birth_snapshot="2004-02-29",
            )
        response = self.post(payload)
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["id"])
        members = list(registration.members.all())
        self.assertEqual(members[0].first_name_snapshot, "Given 2")
        self.assertEqual(members[0].last_name_snapshot, "Nguyễn")
        self.assertEqual(members[0].student_id_snapshot, "002")
        self.assertEqual(members[0].date_of_birth_snapshot, date(2004, 2, 29))
        self.assertEqual(members[0].roster_role, "substitute")
        for member in response.data["members"]:
            self.assertTrue(
                set(member).isdisjoint(
                    {
                        "first_name_snapshot",
                        "last_name_snapshot",
                        "date_of_birth_snapshot",
                        "student_id_snapshot",
                    }
                )
            )
        self.owner.first_name = "Changed profile"
        self.owner.save()
        members[0].refresh_from_db()
        self.assertEqual(members[0].first_name_snapshot, "Given 2")

    def test_student_id_required_for_student_only_tournament_including_substitutes(
        self,
    ):
        payload = self.team_payload()
        tournament = self.tournament_game.tournament
        tournament.students_only = True
        tournament.save()
        payload["members"][2]["student_id_snapshot"] = " "
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("student ID is required", str(response.data))
        self.assertEqual(Registration.objects.count(), 2)
        payload["members"][2]["student_id_snapshot"] = "00123"
        self.assertEqual(self.post(payload).status_code, 201)

    def test_open_tournament_accepts_missing_student_ids(self):
        payload = self.team_payload()
        for member in payload["members"]:
            member.pop("student_id_snapshot")
        response = self.post(payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(
            Registration.objects.get(pk=response.data["id"])
            .members.exclude(student_id_snapshot="")
            .exists()
        )

    def test_open_tournament_accepts_players_without_schools(self):
        payload = self.team_payload()
        payload["members"][0]["institution_label"] = ""
        payload["members"][1].pop("institution_label")
        response = self.post(payload)
        self.assertEqual(response.status_code, 201, response.data)
        members = Registration.objects.get(pk=response.data["id"]).members.all()
        self.assertEqual(
            members.filter(institution__isnull=True, school_snapshot="").count(), 2
        )
        self.assertEqual(members.count(), 3)

    def test_student_only_tournament_still_requires_every_players_school(self):
        payload = self.team_payload()
        tournament = self.tournament_game.tournament
        tournament.students_only = True
        tournament.save(update_fields=("students_only",))
        payload["members"][2]["institution_label"] = ""
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("school", str(response.data).lower())
        self.assertEqual(Registration.objects.count(), 2)

    def test_invalid_substitute_identity_rolls_back_entire_registration(self):
        payload = self.team_payload()
        payload["members"][2]["date_of_birth_snapshot"] = "2999-01-01"
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Registration.objects.count(), 2)
