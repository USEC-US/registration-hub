from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.tests.factories import create_account

from registrations.models import Registration, RegistrationMember
from tournaments.models import Game, Tournament, TournamentGame

class RegistrationMemberModelTests(TestCase):
    def setUp(self):
        self.user = create_account(
            email="captain@example.com",
            password="strong-password",
            first_name="Captain",
            last_name="Player",
        )
        game = Game.objects.create(name="Valorant", slug="valorant")
        tournament = Tournament.objects.create(name="Summer", slug="summer")
        self.tournament_game = TournamentGame.objects.create(
            tournament=tournament,
            game=game,
            team_size_min=5,
            team_size_max=5,
            registration_opens_at=timezone.now(),
            registration_closes_at=timezone.now() + timedelta(days=1),
            fee_amount="0.00",
            fee_currency="VND",
        )
        self.registration = Registration.objects.create(
            tournament_game=self.tournament_game,
            submitted_by=self.user,
            team_name="USEC",
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot="0.00",
            fee_currency_snapshot="VND",
            submitted_at=timezone.now(),
        )

    def test_only_one_captain_is_allowed_per_registration(self):
        RegistrationMember.objects.create(
            registration=self.registration,
            gamer_tag_snapshot="captain",
            school_snapshot="HCMUS",
            is_captain=True,
            display_order=1,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistrationMember.objects.create(
                registration=self.registration,
                gamer_tag_snapshot="second-captain",
                school_snapshot="HCMUS",
                is_captain=True,
                display_order=2,
            )
