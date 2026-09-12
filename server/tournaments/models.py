from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


class Game(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Tournament(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    is_published = models.BooleanField(default=False)
    cover_image = models.ImageField(
        upload_to="tournaments/covers/",
        null=True,
        blank=True,
    )
    is_featured = models.BooleanField(default=False)
    students_only = models.BooleanField(
        default=False,
        help_text="Require a student ID for every player. Organizers review student eligibility.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(starts_at__isnull=True)
                    | Q(ends_at__isnull=True)
                    | Q(starts_at__lt=F("ends_at"))
                ),
                name="tournament_starts_before_ends",
            )
        ]

    def __str__(self) -> str:
        return self.name


class TournamentGame(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="tournament_games"
    )
    game = models.ForeignKey(
        Game, on_delete=models.PROTECT, related_name="tournament_games"
    )
    main_roster_size = models.PositiveSmallIntegerField(
        "main roster size",
        validators=[MinValueValidator(1)],
        help_text="Required number of main players per registration.",
    )
    substitute_limit = models.PositiveSmallIntegerField(
        "maximum substitutes",
        default=0,
        help_text="Optional substitute places; zero means no substitutes.",
    )
    registration_opens_at = models.DateTimeField()
    registration_closes_at = models.DateTimeField()
    registration_capacity = models.PositiveIntegerField(null=True, blank=True)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee_currency = models.CharField(max_length=3, default="VND")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tournament", "game"),
                name="unique_tournament_game",
            ),
            models.CheckConstraint(
                condition=Q(main_roster_size__gte=1),
                name="tournament_game_main_roster_positive",
            ),
            models.CheckConstraint(
                condition=Q(substitute_limit__gte=0),
                name="tournament_game_substitute_limit_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(registration_opens_at__lt=F("registration_closes_at")),
                name="tournament_game_registration_window_valid",
            ),
            models.CheckConstraint(
                condition=Q(registration_capacity__isnull=True)
                | Q(registration_capacity__gt=0),
                name="tournament_game_capacity_positive_or_null",
            ),
            models.CheckConstraint(
                condition=Q(fee_amount__gte=0),
                name="tournament_game_fee_non_negative",
            ),
        ]

    @property
    def is_individual(self) -> bool:
        return self.main_roster_size == 1 and self.substitute_limit == 0

    @property
    def is_team(self) -> bool:
        return not self.is_individual

    def __str__(self) -> str:
        return f"{self.tournament} / {self.game}"
