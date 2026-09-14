from datetime import date
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APITestCase

from accounts.models import Institution
from registrations.models import PaymentAttempt, Registration

from . import test_api
from .images import payment_image


@override_settings(DEBUG=True, TURNSTILE_SECRET_KEY="")
class GuestSubmissionTests(APITestCase):
    setUp = test_api.RegistrationOwnershipApiTests.setUp
    _create_registration = test_api.RegistrationOwnershipApiTests._create_registration

    def payload(self):
        return {
            "tournament_game": self.tournament_game.pk,
            "team_name": "",
            "submitter_role": "captain",
            "contact_facebook_snapshot": "fb/me",
            "contact_phone_snapshot": "0901234567",
            "members": [
                {
                    "gamer_tag_snapshot": "new-player",
                    "first_name_snapshot": "Player",
                    "last_name_snapshot": "Example",
                    "date_of_birth_snapshot": "2005-01-01",
                    "student_id_snapshot": "0012345",
                    "institution_label": "New school",
                    "is_captain": True,
                    "display_order": 1,
                }
            ],
        }

    def post(self, payload=None, proof=None):
        payload = self.payload() if payload is None else payload
        if proof:
            if (
                "payment_intent_token" not in payload
                and self.tournament_game.fee_amount > 0
            ):
                from registrations.payments import create_payment_intent

                payload["payment_intent_token"] = str(
                    create_payment_intent(tournament_game=self.tournament_game).token
                )
            return self.client.post(
                "/api/registrations/submit/",
                {
                    "payload": json.dumps(payload),
                    "proof_file": proof,
                    "reference": "private-ref",
                },
                format="multipart",
            )
        return self.client.post("/api/registrations/submit/", payload, format="json")

    def test_paid_guest_without_initial_proof_gets_timed_reservation(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertIsNotNone(registration.payment_due_at)
        self.assertEqual(registration.payment_hold_minutes_snapshot, 60)
        self.assertFalse(registration.payment_attempts.exists())
        self.assertEqual(Registration.objects.count(), 3)

    def team_payload(self):
        self.tournament_game.main_roster_size = 2
        self.tournament_game.substitute_limit = 1
        self.tournament_game.fee_amount = 0
        self.tournament_game.save()
        payload = self.payload()
        payload.update(
            team_name="Team",
            team_tag="TEAM",
            submitter_role="manager",
            manager_name_snapshot="Manager",
        )
        payload["members"] = [
            {
                **payload["members"][0],
                "gamer_tag_snapshot": f"player-{index}",
                "display_order": index,
                "is_captain": index == 3,
                "roster_role": "substitute" if index == 3 else "main",
            }
            for index in (1, 2, 3)
        ]
        return payload

    def test_team_tags_are_required_ascii_uppercase_and_not_unique(self):
        payload = self.team_payload()
        for tag in ("", "A", "ABCDEF", "A-B", "ĐH", "A B", "ßa", "ＡB"):
            with self.subTest(tag=tag):
                payload["team_tag"] = tag
                response = self.post(payload)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("team_tag", response.data)
        for tag in ("ab", "ab", "a1234"):
            payload["team_tag"] = tag
            for member in payload["members"]:
                member["gamer_tag_snapshot"] += "x"
            response = self.post(payload)
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["team_tag"], tag.upper())
            self.assertEqual(
                Registration.objects.get(pk=response.data["id"]).team_tag, tag.upper()
            )

    def test_solo_registration_rejects_team_tag(self):
        payload = self.payload()
        payload["team_tag"] = "AB"
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("team_tag", response.data)

    def test_substitute_representative_saved_first_and_roles_survive_config_change(
        self,
    ):
        payload = self.team_payload()
        response = self.post(payload)
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["id"])
        members = list(registration.members.all())
        self.assertEqual([m.display_order for m in members], [1, 2, 3])
        self.assertTrue(members[0].is_captain)
        self.assertEqual(members[0].roster_role, "substitute")
        self.assertEqual(members[0].gamer_tag_snapshot, "player-3")
        self.assertTrue(all(m.user_id is None for m in members))
        self.tournament_game.main_roster_size = 3
        self.tournament_game.substitute_limit = 0
        self.tournament_game.save()
        members[0].refresh_from_db()
        self.assertEqual(members[0].roster_role, "substitute")

    def test_substitute_duplicate_blocks_other_team_main_player(self):
        payload = self.team_payload()
        self.assertEqual(self.post(payload).status_code, 201)
        payload["members"] = [
            {
                **payload["members"][0],
                "gamer_tag_snapshot": "player-3",
                "is_captain": True,
            },
            {**payload["members"][1], "gamer_tag_snapshot": "new-main"},
        ]
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("already has an active registration", str(response.data))

    def test_signed_captain_can_be_substitute_in_slot_one(self):
        payload = self.team_payload()
        payload.update(submitter_role="captain", manager_name_snapshot="")
        payload["members"] = [payload["members"][2], *payload["members"][:2]]
        for index, member in enumerate(payload["members"], 1):
            member["display_order"] = index
        self.client.force_authenticate(self.owner)
        response = self.post(payload)
        self.assertEqual(response.status_code, 201, response.data)
        member = Registration.objects.get(pk=response.data["id"]).members.get(
            display_order=1
        )
        self.assertEqual(member.user_id, self.owner.pk)
        self.assertEqual(member.roster_role, "substitute")

    def test_roster_roles_are_validated_before_creating_registration(self):
        payload = self.team_payload()
        for roles in (
            ("main", "substitute", "substitute"),
            ("main", "main", "main"),
            ("main", "main", "invalid"),
        ):
            with self.subTest(roles=roles):
                for member, role in zip(payload["members"], roles):
                    member["roster_role"] = role
                response = self.post(payload)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(Registration.objects.count(), 2)

    def test_paid_guest_atomic_proof_and_private_response(self):
        response = self.post(proof=payment_image())
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["id"])
        self.assertIsNone(registration.submitted_by_id)
        self.assertIsNone(registration.status_events.get().actor_id)
        self.assertEqual(registration.contact_phone_snapshot, "0901234567")
        self.assertEqual(
            registration.payment_attempts.get().amount, self.tournament_game.fee_amount
        )
        self.assertEqual(registration.members.get().school_snapshot, "New school")
        self.assertNotIn("contact_phone_snapshot", response.data)
        self.assertNotIn("proof_file", str(response.data))
        self.assertIn(
            self.client.get(
                registration.payment_attempts.get().proof_file.url
            ).status_code,
            (401, 403),
        )

    def test_free_guest_and_signed_captain_and_manager(self):
        self.tournament_game.fee_amount = 0
        self.tournament_game.save()
        for index, role in enumerate(("captain", "captain", "manager")):
            self.client.force_authenticate(self.owner if index else None)
            payload = self.payload()
            payload["submitter_role"] = role
            payload["manager_name_snapshot"] = "Manager" if role == "manager" else ""
            payload["members"][0]["gamer_tag_snapshot"] += str(index)
            response = self.post(payload)
            self.assertEqual(response.status_code, 201, response.data)
            registration = Registration.objects.get(pk=response.data["id"])
            self.assertEqual(
                registration.members.get().user_id,
                self.owner.pk if index == 1 else None,
            )

    def test_required_contacts_and_manager_name(self):
        self.client.force_authenticate(self.owner)
        for field in (
            "contact_facebook_snapshot",
            "contact_phone_snapshot",
            "submitter_role",
        ):
            payload = self.payload()
            payload.pop(field)
            response = self.post(payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.data)
        payload = self.payload()
        payload["submitter_role"] = "manager"
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("manager_name_snapshot", response.data)

    def test_duplicates_normalized_and_rejected_releases_claim(self):
        self.client.force_authenticate(self.owner)
        first = self.post()
        self.assertEqual(first.status_code, 201, first.data)
        payload = self.payload()
        payload["members"][0]["gamer_tag_snapshot"] = "  NEW-player  "
        payload["members"][0]["institution_label"] = " new   SCHOOL "
        self.assertEqual(self.post(payload).status_code, 400)
        registration = Registration.objects.get(pk=first.data["id"])
        from registrations.services import reject_registration, start_review

        self.owner.is_superuser = True
        start_review(actor=self.owner, registration_id=registration.pk)
        reject_registration(
            actor=self.owner,
            registration_id=registration.pk,
            note="Correct roster and resubmit",
        )
        self.assertEqual(registration.status_events.count(), 3)
        self.assertEqual(self.post(payload).status_code, 201)

    def test_invalid_proof_leaves_no_registration_or_institution(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.post(proof=SimpleUploadedFile("proof.png", b"bad"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Registration.objects.count(), 2)
        self.assertFalse(Institution.objects.filter(label="New school").exists())

    def test_failed_insert_cleans_stored_proof(self):
        from django.conf import settings

        original = PaymentAttempt.save

        def fail_after_save(instance, *args, **kwargs):
            original(instance, *args, **kwargs)
            raise RuntimeError("database failure after file save")

        with (
            patch.object(PaymentAttempt, "save", fail_after_save),
            self.assertRaises(RuntimeError),
        ):
            self.post(proof=payment_image())
        self.assertEqual(Registration.objects.count(), 2)
        self.assertEqual(
            [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()], []
        )

    def test_institution_snapshot_stays_and_identity_blocks_after_rename(self):
        self.client.force_authenticate(self.owner)
        institution = Institution.objects.create(
            label="A" * 200, review_status="VERIFIED"
        )
        payload = self.payload()
        payload["members"][0].pop("institution_label")
        payload["members"][0]["institution_id"] = institution.pk
        first = self.post(payload)
        self.assertEqual(first.status_code, 201, first.data)
        institution.label = "Renamed"
        institution.save()
        member = Registration.objects.get(pk=first.data["id"]).members.get()
        self.assertEqual(member.school_snapshot, "A" * 200)
        self.assertEqual(self.post(payload).status_code, 400)

    def test_historical_snapshot_blocks_duplicate(self):
        self.registration.members.create(
            gamer_tag_snapshot=" NEW-player ",
            school_snapshot="new   school",
            is_captain=True,
            display_order=1,
        )
        self.client.force_authenticate(self.owner)
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("members", response.data)

    def test_captain_slot_and_within_roster_duplicates(self):
        self.client.force_authenticate(self.owner)
        self.tournament_game.main_roster_size = 2
        self.tournament_game.substitute_limit = 0
        self.tournament_game.save()
        payload = self.payload()
        payload["team_name"] = "Team"
        payload["team_tag"] = "TEAM"
        payload["members"].append(
            {**payload["members"][0], "display_order": 2, "is_captain": False}
        )
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("members", response.data)
        payload["members"][1]["gamer_tag_snapshot"] = "Different"
        payload["members"][0]["is_captain"] = False
        payload["members"][1]["is_captain"] = True
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("members", response.data)
        payload["submitter_role"] = "manager"
        payload["manager_name_snapshot"] = "Manager"
        self.assertEqual(self.post(payload).status_code, 201)

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="")
    def test_guest_turnstile_prevents_institution_side_effect(self):
        response = self.post(proof=payment_image())
        self.assertEqual(response.status_code, 400)
        self.assertIn("turnstile_token", response.data)
        self.assertFalse(Institution.objects.filter(label="New school").exists())

    def test_free_proof_rejected_and_malformed_envelope(self):
        self.tournament_game.fee_amount = 0
        self.tournament_game.save()
        response = self.post(proof=payment_image())
        self.assertEqual(response.status_code, 400)
        self.assertIn("proof_file", response.data)
        response = self.client.post(
            "/api/registrations/submit/", {"payload": "oops"}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("payload", response.data)


class ConcurrentGuestSubmissionTests(TransactionTestCase):
    setUp = test_api.RegistrationOwnershipApiTests.setUp
    _create_registration = test_api.RegistrationOwnershipApiTests._create_registration

    def test_concurrent_identical_players_have_one_active_claim(self):
        from django.core.exceptions import ValidationError

        from registrations.services import RegistrationMemberInput, submit_registration

        self.tournament_game.fee_amount = 0
        self.tournament_game.save()
        barrier = Barrier(2)
        division_id = self.tournament_game.pk

        def submit():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    registration = submit_registration(
                        submitted_by=None,
                        tournament_game_id=division_id,
                        team_name="",
                        submitter_role="captain",
                        contact_facebook_snapshot="fb/me",
                        contact_phone_snapshot="0901234567",
                        members=[
                            RegistrationMemberInput(
                                first_name_snapshot="Player",
                                last_name_snapshot="Example",
                                date_of_birth_snapshot=date(2005, 1, 1),
                                student_id_snapshot="0012345",
                                gamer_tag_snapshot="same-player",
                                institution_label="Race school",
                                is_captain=True,
                                display_order=1,
                            )
                        ],
                    )
                    return registration.pk
                except ValidationError:
                    return None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(sum(pk is not None for pk in outcomes), 1)
        self.assertEqual(
            Registration.objects.filter(
                members__gamer_tag_snapshot="same-player"
            ).count(),
            1,
        )
