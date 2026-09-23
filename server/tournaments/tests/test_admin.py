from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tests.factories import create_account
from registrations.models import Registration
from tournaments.admin import GameAdmin, TournamentAdmin, TournamentGameInline
from tournaments.models import Game, Tournament, TournamentGame


class TournamentAdminAccessTests(TestCase):
    def test_direct_catalog_permissions_do_not_bypass_organizer_membership(self):
        staff_user = create_account(
            email="catalog-staff@example.com",
            password="strong-password",
            first_name="Catalog",
            last_name="Staff",
            is_staff=True,
        )
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="tournaments", codename="view_game"
            ),
            Permission.objects.get(
                content_type__app_label="tournaments", codename="change_game"
            ),
        )
        game = Game.objects.create(name="Chess", slug="chess")
        request = RequestFactory().get("/admin/tournaments/game/")
        request.user = staff_user
        model_admin = GameAdmin(Game, AdminSite())

        self.assertFalse(model_admin.has_module_permission(request))
        self.assertFalse(model_admin.has_view_permission(request, game))
        self.assertFalse(model_admin.has_change_permission(request, game))

    def test_tournament_admin_exposes_tournament_game_inline(self):
        model_admin = TournamentAdmin(Tournament, AdminSite())
        inline = TournamentGameInline(Tournament, AdminSite())

        self.assertIn(TournamentGameInline, model_admin.inlines)
        self.assertIs(inline.model, TournamentGame)
        self.assertEqual(
            inline.fields,
            (
                "game",
                "main_roster_size",
                "substitute_limit",
                "registration_opens_at",
                "registration_closes_at",
                "registration_capacity",
                "fee_amount",
                "fee_currency",
            ),
        )


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class OrganizerNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = create_account(is_staff=True)
        group = Group.objects.create(name="Organizers")
        group.permissions.add(
            *Permission.objects.filter(
                codename__in=(
                    "view_tournament",
                    "view_tournamentgame",
                    "view_registration",
                )
            )
        )
        cls.organizer.groups.add(group)
        cls.tournament = Tournament.objects.create(name="Summer", slug="summer")
        cls.empty = Tournament.objects.create(name="Empty", slug="empty")
        cls.divisions = []
        for index in range(4):
            cls.divisions.append(
                TournamentGame.objects.create(
                    tournament=cls.tournament if index < 2 else cls.empty,
                    game=Game.objects.create(
                        name=f"Game {index}", slug=f"game-{index}"
                    ),
                    main_roster_size=1,
                    registration_opens_at=timezone.now(),
                    registration_closes_at=timezone.now() + timedelta(days=1),
                    fee_amount=0,
                )
            )
        cls.registrations = [
            Registration.objects.create(
                tournament_game=cls.divisions[index % 2],
                status=status,
                fee_amount_snapshot=0,
                fee_currency_snapshot="VND",
            )
            for index, status in enumerate(Registration.Status.values)
        ]
        Registration.objects.create(
            tournament_game=cls.divisions[3],
            status=Registration.Status.SUBMITTED,
            fee_amount_snapshot=0,
            fee_currency_snapshot="VND",
        )
        cls.no_divisions = Tournament.objects.create(name="New", slug="new")

    def setUp(self):
        self.client.force_login(self.organizer)

    def test_counts_and_links_on_lists_and_detail_pages(self):
        tournament_admin = admin.site.get_model_admin(Tournament)
        division_admin = admin.site.get_model_admin(TournamentGame)
        request = RequestFactory().get("/admin/")
        request.user = self.organizer
        tournament = tournament_admin.get_queryset(request).get(pk=self.tournament.pk)
        division = division_admin.get_queryset(request).get(pk=self.divisions[0].pk)
        cases = (
            (
                Tournament,
                tournament,
                "division_count",
                2,
                "admin:tournaments_tournamentgame_changelist",
                {"tournament__id__exact": tournament.pk},
                {item.pk for item in self.divisions[:2]},
            ),
            (
                Tournament,
                tournament,
                "registration_count",
                5,
                "admin:registrations_registration_changelist",
                {"tournament_game__tournament__id__exact": tournament.pk},
                {item.pk for item in self.registrations},
            ),
            (
                TournamentGame,
                division,
                "registration_count",
                3,
                "admin:registrations_registration_changelist",
                {"tournament_game__id__exact": division.pk},
                {item.pk for item in self.registrations[::2]},
            ),
        )
        for model, obj, field, count, target, query, expected in cases:
            with self.subTest(model=model, field=field):
                model_admin = admin.site.get_model_admin(model)
                url = reverse(target, query=query)
                with self.assertNumQueries(0):
                    link = getattr(model_admin, field)(obj)
                self.assertHTMLEqual(link, f'<a href="{url}">{count}</a>')
                for page in (
                    reverse(f"admin:tournaments_{model._meta.model_name}_changelist"),
                    reverse(
                        f"admin:tournaments_{model._meta.model_name}_change",
                        args=[obj.pk],
                    ),
                ):
                    self.assertContains(self.client.get(page), link, html=True)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertSetEqual(
                    {item.pk for item in response.context["cl"].result_list}, expected
                )

    def test_empty_and_unsaved_objects(self):
        request = RequestFactory().get("/admin/")
        request.user = self.organizer
        for model, pk, fields in (
            (
                Tournament,
                self.no_divisions.pk,
                ("division_count", "registration_count"),
            ),
            (TournamentGame, self.divisions[2].pk, ("registration_count",)),
        ):
            model_admin = admin.site.get_model_admin(model)
            obj = model_admin.get_queryset(request).get(pk=pk)
            for field in fields:
                with self.subTest(model=model, field=field), self.assertNumQueries(0):
                    self.assertIn(">0</a>", getattr(model_admin, field)(obj))
                    self.assertEqual(getattr(model_admin, field)(model()), "—")

    def test_filtered_registration_links_keep_permission_gates(self):
        url = reverse(
            "admin:registrations_registration_changelist",
            query={"tournament_game__id__exact": self.divisions[0].pk},
        )
        # Organizer membership alone is insufficient to read registrations.
        self.organizer.groups.get().permissions.remove(
            Permission.objects.get(codename="view_registration")
        )
        self.assertEqual(self.client.get(url).status_code, 403)
        # Direct model permission alone is also insufficient without membership.
        self.organizer.groups.clear()
        self.organizer.user_permissions.add(
            Permission.objects.get(codename="view_registration")
        )
        self.assertEqual(self.client.get(url).status_code, 403)
