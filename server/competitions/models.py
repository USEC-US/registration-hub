from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Competition(models.Model):
    tournament_game = models.OneToOneField(
        "tournaments.TournamentGame",
        on_delete=models.PROTECT,
        related_name="competition",
    )
    revision = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Competition for {self.tournament_game}"


class CompetitionEntrant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"
        DISQUALIFIED = "DISQUALIFIED", "Disqualified"

    competition = models.ForeignKey(
        Competition, on_delete=models.PROTECT, related_name="entrants"
    )
    registration = models.ForeignKey(
        "registrations.Registration",
        on_delete=models.PROTECT,
        related_name="competition_entries",
    )
    display_name = models.CharField(max_length=100)
    display_tag = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    selected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("competition", "registration"),
                name="unique_competition_registration",
            )
        ]

    def __str__(self) -> str:
        return self.display_name


class Stage(models.Model):
    class Format(models.TextChoices):
        SINGLE_ELIMINATION = "SINGLE_ELIMINATION", "Single elimination"
        DOUBLE_ELIMINATION = "DOUBLE_ELIMINATION", "Double elimination"
        ROUND_ROBIN = "ROUND_ROBIN", "Round robin"
        SWISS_FIXED = "SWISS_FIXED", "Swiss (fixed rounds)"
        SWISS_THRESHOLD = "SWISS_THRESHOLD", "Swiss (win/loss thresholds)"

    class SeriesMode(models.TextChoices):
        BEST_OF = "BEST_OF", "Best of"
        FIXED_GAMES = "FIXED_GAMES", "Fixed games"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        READY = "READY", "Ready"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        AWAITING = "AWAITING", "Awaiting resolution"
        COMPLETE = "COMPLETE", "Complete"

    competition = models.ForeignKey(
        Competition, on_delete=models.PROTECT, related_name="stages"
    )
    sequence = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    name = models.CharField(max_length=100)
    format = models.CharField(max_length=24, choices=Format.choices)
    series_mode = models.CharField(max_length=16, choices=SeriesMode.choices)
    default_series_length = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)]
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    champion = models.ForeignKey(
        CompetitionEntrant,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="championships",
    )
    completed_without_champion = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("sequence", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("competition", "sequence"),
                name="unique_competition_stage_sequence",
            ),
            models.CheckConstraint(
                condition=Q(default_series_length__gte=1),
                name="stage_series_length_positive",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class StageDraw(models.Model):
    class State(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name="draws")
    version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.DRAFT
    )
    randomized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("version", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("stage", "version"), name="unique_stage_draw_version"
            ),
            models.UniqueConstraint(
                fields=("stage",),
                condition=~Q(state="SUPERSEDED"),
                name="one_current_stage_draw",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.stage} draw v{self.version}"


class StageEntry(models.Model):
    draw = models.ForeignKey(
        StageDraw, on_delete=models.PROTECT, related_name="entries"
    )
    entrant = models.ForeignKey(
        CompetitionEntrant, on_delete=models.PROTECT, related_name="stage_entries"
    )
    seed = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    source_entry = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="advanced_entries",
    )

    class Meta:
        ordering = ("seed", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("draw", "entrant"), name="unique_draw_entrant"
            ),
            models.UniqueConstraint(fields=("draw", "seed"), name="unique_draw_seed"),
        ]

    def __str__(self) -> str:
        return f"#{self.seed} {self.entrant}"


class Round(models.Model):
    class Section(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        TIEBREAK = "TIEBREAK", "Tiebreak"

    draw = models.ForeignKey(StageDraw, on_delete=models.PROTECT, related_name="rounds")
    number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    section = models.CharField(
        max_length=16, choices=Section.choices, default=Section.NORMAL
    )
    series_length_override = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )

    class Meta:
        ordering = ("number", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("draw", "section", "number"), name="unique_draw_round"
            ),
            models.CheckConstraint(
                condition=Q(series_length_override__isnull=True)
                | Q(series_length_override__gte=1),
                name="round_series_override_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.draw} round {self.number}"


class Match(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        LIVE = "LIVE", "Live"
        FINAL = "FINAL", "Final"

    class Outcome(models.TextChoices):
        PLAYED = "PLAYED", "Played"
        FORFEIT = "FORFEIT", "Forfeit"
        DOUBLE_FORFEIT = "DOUBLE_FORFEIT", "Double forfeit"
        BYE = "BYE", "Bye"
        EMPTY = "EMPTY", "Empty"

    round = models.ForeignKey(Round, on_delete=models.PROTECT, related_name="matches")
    number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    code = models.CharField(max_length=64, unique=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    series_length_override = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    applied_series_length = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    side_one_score = models.PositiveSmallIntegerField(null=True, blank=True)
    side_two_score = models.PositiveSmallIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    winner = models.ForeignKey(
        StageEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="won_matches",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("round__number", "number", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("round", "number"), name="unique_round_match"
            ),
            models.CheckConstraint(
                condition=Q(series_length_override__isnull=True)
                | Q(series_length_override__gte=1),
                name="match_series_override_positive",
            ),
            models.CheckConstraint(
                condition=Q(applied_series_length__isnull=True)
                | Q(applied_series_length__gte=1),
                name="match_applied_series_positive",
            ),
        ]

    @property
    def effective_series_length(self) -> int:
        return (
            self.applied_series_length
            or self.series_length_override
            or self.round.series_length_override
            or self.round.draw.stage.default_series_length
        )

    def __str__(self) -> str:
        return self.code


class MatchSlot(models.Model):
    class SourceOutcome(models.TextChoices):
        WINNER = "WINNER", "Winner"

    match = models.ForeignKey(Match, on_delete=models.PROTECT, related_name="slots")
    position = models.PositiveSmallIntegerField()
    entry = models.ForeignKey(
        StageEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="direct_match_slots",
    )
    source_match = models.ForeignKey(
        Match,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="dependent_slots",
    )
    source_outcome = models.CharField(
        max_length=12, choices=SourceOutcome.choices, blank=True
    )
    is_empty = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    resolved_entry = models.ForeignKey(
        StageEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resolved_match_slots",
    )

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("match", "position"), name="unique_match_slot_position"
            ),
            models.CheckConstraint(
                condition=Q(position__in=(1, 2)), name="match_slot_position_one_or_two"
            ),
            models.CheckConstraint(
                condition=(
                    Q(entry__isnull=False, source_match__isnull=True, is_empty=False)
                    | Q(entry__isnull=True, source_match__isnull=False, is_empty=False)
                    | Q(entry__isnull=True, source_match__isnull=True, is_empty=True)
                ),
                name="match_slot_has_one_source",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.match} slot {self.position}"


class ChangeSet(models.Model):
    competition = models.ForeignKey(
        Competition, on_delete=models.PROTECT, related_name="changes"
    )
    revision = models.PositiveBigIntegerField()
    kind = models.CharField(max_length=40)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="competition_changes",
    )
    internal_reason = models.TextField(blank=True)
    private_data = models.JSONField(default=dict)
    public_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("revision", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("competition", "revision"),
                name="unique_competition_change_revision",
            )
        ]

    def __str__(self) -> str:
        return f"{self.competition} revision {self.revision}"
