from django import forms
from django.utils import timezone

from registrations.models import Registration
from tournaments.models import TournamentGame

from .admin_workspace import slot_label
from .commands import _entrant_label
from .models import CompetitionEntrant, Match, Stage, StageDraw, TieResolution
from .command_support import _validate_series_length
from .round_robin import DEFAULT_TIEBREAKS
from .round_robin_commands import group_standings

TIEBREAK_CHOICES = (
    ("", "No rule"),
    ("HEAD_TO_HEAD", "Head-to-head points"),
    ("MATCH_WINS", "Match wins"),
    ("GAME_DIFFERENCE", "Game difference"),
    ("GAMES_WON", "Games won"),
)


class NewCompetitionForm(forms.Form):
    tournament_game = forms.ModelChoiceField(
        label="Tournament division",
        queryset=TournamentGame.objects.none(),
        help_text="Choose the tournament and game whose approved entrants will compete.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tournament_game"].queryset = (
            TournamentGame.objects.filter(competition__isnull=True)
            .select_related("tournament", "game")
            .order_by("tournament__name", "game__name")
        )


class RevisionForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class CompetitionSetupForm(RevisionForm):
    name = forms.CharField(label="Stage name", max_length=100, initial="Final bracket")
    format = forms.ChoiceField(
        required=False,
        choices=(
            (Stage.Format.SINGLE_ELIMINATION, "Single elimination"),
            (Stage.Format.DOUBLE_ELIMINATION, "Double elimination"),
            (Stage.Format.ROUND_ROBIN, "Round robin"),
        ),
        initial=Stage.Format.SINGLE_ELIMINATION,
    )
    grand_final_policy = forms.ChoiceField(
        label="Grand final policy",
        required=False,
        choices=(("", "Choose a grand final policy"), *Stage.GrandFinalPolicy.choices),
        help_text="Required for double elimination; leave blank for single elimination.",
    )
    default_series_length = forms.IntegerField(
        label="Games per match",
        min_value=1,
        initial=3,
        help_text="Use 1, 3, 5, … For best of 3, the first to 2 game wins advances.",
    )

    series_mode = forms.ChoiceField(
        required=False, choices=Stage.SeriesMode.choices, initial="BEST_OF"
    )
    meetings = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=1,
        choices=((1, "Single round robin"), (2, "Double round robin")),
        initial=1,
    )
    win_points = forms.DecimalField(
        required=False, decimal_places=2, max_digits=10, min_value=0, initial=3
    )
    draw_points = forms.DecimalField(
        required=False, decimal_places=2, max_digits=10, min_value=0, initial=1
    )
    loss_points = forms.DecimalField(
        required=False, decimal_places=2, max_digits=10, min_value=0, initial=0
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for index in range(1, 5):
            self.fields[f"tiebreak_{index}"] = forms.ChoiceField(
                label=f"Tiebreaker {index}",
                required=False,
                choices=TIEBREAK_CHOICES,
                initial=DEFAULT_TIEBREAKS[index - 1] if index <= 3 else "",
            )
        self.fields[
            "tiebreak_1"
        ].help_text = "Head-to-head points uses only entrants still tied. Each criterion runs once; it does not restart after separation."
        self.fields[
            "tiebreak_2"
        ].help_text = "Match wins includes played and forfeit wins. Game difference is completed played game wins minus losses."
        self.fields[
            "tiebreak_3"
        ].help_text = "Games won counts completed played games. Live and partial forfeit scores do not count."

    def clean(self):
        cleaned = super().clean()
        format_ = cleaned.get("format") or Stage.Format.SINGLE_ELIMINATION
        policy = cleaned.get("grand_final_policy", "")
        cleaned["format"] = format_
        mode = (
            (cleaned.get("series_mode") or "BEST_OF")
            if format_ == "ROUND_ROBIN"
            else "BEST_OF"
        )
        cleaned["series_mode"] = mode
        length = cleaned.get("default_series_length")
        if length is not None:
            try:
                _validate_series_length(mode, length)
            except forms.ValidationError as error:
                self.add_error("default_series_length", error)
        rules = [
            cleaned.get(f"tiebreak_{i}")
            for i in range(1, 5)
            if cleaned.get(f"tiebreak_{i}")
        ]
        cleaned["tiebreaks"] = rules
        if len(set(rules)) != len(rules):
            self.add_error(None, "Choose each supported tiebreaker at most once.")
        if format_ == "ROUND_ROBIN":
            for field in ("win_points", "draw_points", "loss_points"):
                if cleaned.get(field) is None:
                    self.add_error(field, "Enter the points for this result.")
        if format_ == Stage.Format.DOUBLE_ELIMINATION and not policy:
            self.add_error("grand_final_policy", "Choose reset or no reset.")
        elif format_ == Stage.Format.SINGLE_ELIMINATION and policy:
            self.add_error(
                "grand_final_policy", "Single elimination has no final policy."
            )
        return cleaned


class EntrantChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, registration):
        try:
            return _entrant_label(registration)[0]
        except forms.ValidationError:
            return "Unnamed entrant"


class EntrantSelectionForm(RevisionForm):
    registrations = EntrantChoiceField(
        label="Approved entrants",
        help_text="Select the players or teams to include in this bracket.",
        queryset=Registration.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, competition, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["registrations"].queryset = (
            Registration.objects.filter(
                tournament_game=competition.tournament_game,
                status=Registration.Status.APPROVED,
            )
            .select_related("tournament_game")
            .prefetch_related("members")
            .order_by("team_name", "pk")
        )


class DrawForm(RevisionForm):
    randomize = forms.BooleanField(
        label="Shuffle entrants randomly",
        required=False,
        help_text="Leave unchecked to use the seed order below. Seed 1 is the highest-ranked entrant.",
    )

    def __init__(self, *args, competition, **kwargs):
        super().__init__(*args, **kwargs)
        self.entrants = list(
            CompetitionEntrant.objects.filter(
                competition=competition, is_selected=True
            ).order_by("pk")
        )
        choices = [(entrant.pk, str(entrant)) for entrant in self.entrants]
        draw = competition.stages.filter(sequence=1).first()
        draw = (
            draw.draws.exclude(state=StageDraw.State.SUPERSEDED).first()
            if draw
            else None
        )
        saved_order = (
            list(draw.entries.order_by("seed").values_list("entrant_id", flat=True))
            if draw
            else []
        )
        if set(saved_order) != {item.pk for item in self.entrants}:
            saved_order = [item.pk for item in self.entrants]
        for seed in range(1, len(self.entrants) + 1):
            self.fields[f"seed_{seed}"] = forms.ChoiceField(
                label=f"Seed {seed}",
                choices=choices,
                initial=saved_order[seed - 1],
                required=not (self.is_bound and self.data.get("randomize")),
            )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("randomize"):
            return cleaned
        order = [
            int(cleaned[f"seed_{seed}"])
            for seed in range(1, len(self.entrants) + 1)
            if f"seed_{seed}" in cleaned
        ]
        if len(order) != len(self.entrants) or len(order) != len(set(order)):
            raise forms.ValidationError("Choose every entrant exactly once.")
        cleaned["entrant_order"] = order
        return cleaned


class GroupDrawForm(DrawForm):
    group_specs = forms.CharField(
        label="Groups and qualifying places",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One group per line: name | qualifying places. Every group needs at least two entrants.",
        initial="Group A | 1",
    )
    allocation = forms.ChoiceField(
        label="Group allocation",
        choices=(
            ("SNAKE", "Seeded snake allocation"),
            ("MANUAL", "Manual assignments"),
        ),
        initial="SNAKE",
    )

    def __init__(self, *args, competition, **kwargs):
        super().__init__(*args, competition=competition, **kwargs)
        stage = competition.stages.first()
        draw = stage.draws.exclude(state="SUPERSEDED").first() if stage else None
        groups = list(draw.groups.all()) if draw else []
        specs = (
            self.data.get("group_specs", "")
            if self.is_bound
            else (
                "\n".join(f"{g.name} | {g.qualifying_places}" for g in groups)
                or "Group A | 1"
            )
        )
        self.initial.setdefault("group_specs", specs)
        choices = [
            (index, line.split("|")[0].strip() or f"Group {index}")
            for index, line in enumerate(
                (line for line in specs.splitlines() if line.strip()), 1
            )
        ]
        saved = (
            dict(draw.entries.values_list("entrant_id", "group__number"))
            if draw
            else {}
        )
        for entry in self.entrants:
            self.fields[f"group_{entry.pk}"] = forms.TypedChoiceField(
                label=f"Group for {entry.display_name}",
                choices=choices,
                coerce=int,
                initial=saved.get(entry.pk, 1),
                required=self.is_bound and self.data.get("allocation") == "MANUAL",
            )

    def clean(self):
        cleaned = super().clean()
        specs = []
        try:
            for line in cleaned.get("group_specs", "").splitlines():
                if line.strip():
                    name, places = line.rsplit("|", 1)
                    specs.append((name.strip(), int(places.strip())))
        except ValueError:
            self.add_error("group_specs", "Use one name | qualifying places per line.")
        cleaned["group_specs"] = specs
        cleaned["ordered_entrant_ids"] = cleaned.pop(
            "entrant_order", [entry.pk for entry in self.entrants]
        )
        if cleaned.get("allocation") == "MANUAL":
            if cleaned.get("randomize"):
                self.add_error(
                    "randomize",
                    "Randomization cannot be combined with manual assignments.",
                )
            cleaned["memberships"] = [
                [
                    entry.pk
                    for entry in self.entrants
                    if cleaned.get(f"group_{entry.pk}") == index
                ]
                for index in range(1, len(specs) + 1)
            ]
        else:
            cleaned["memberships"] = None
        return cleaned


class GroupTieForm(RevisionForm):
    method = forms.ChoiceField(
        label="Resolve qualification tie", choices=TieResolution.Method.choices
    )
    series_length = forms.IntegerField(
        label="Extra contests: best of",
        min_value=1,
        max_value=32767,
        initial=1,
        required=False,
    )

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        state = group_standings(group)
        self.tie = next(
            (tie for tie in state["cutoff_ties"] if tie["resolution_id"] is None), None
        )
        entries = {
            entry.pk: entry.entrant.display_name
            for entry in group.entries.select_related("entrant")
        }
        if self.tie:
            choices = [(pk, entries[pk]) for pk in self.tie["entry_ids"]]
            for index, pk in enumerate(self.tie["entry_ids"], 1):
                self.fields[f"order_{index}"] = forms.TypedChoiceField(
                    label=f"Organizer decision: position {index}",
                    coerce=int,
                    choices=choices,
                    initial=pk,
                    required=self.is_bound and self.data.get("method") == "MANUAL",
                )

    def clean(self):
        cleaned = super().clean()
        if self.tie is None:
            raise forms.ValidationError(
                "This group has no qualification tie awaiting a choice."
            )
        cleaned["tied_entry_ids"] = self.tie["entry_ids"]
        cleaned["parent_resolution_id"] = self.tie["parent_resolution_id"]
        cleaned["ordered_entry_ids"] = (
            [
                cleaned.get(f"order_{i}")
                for i in range(1, len(self.tie["entry_ids"]) + 1)
            ]
            if cleaned.get("method") == "MANUAL"
            else []
        )
        cleaned["series_length"] = cleaned.get("series_length") or 1
        return cleaned


class TieReasonForm(forms.Form):
    internal_reason = forms.CharField(
        label="Private organizer reason",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Required for an organizer decision. Only authorized organizers can see this note.",
    )


class ScheduleForm(RevisionForm):
    scheduled_at = forms.DateTimeField(
        label="Match start time",
        help_text="Leave blank to remove the scheduled time.",
        required=False,
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            "scheduled_at"
        ].help_text = f"Time zone: {timezone.get_current_timezone_name()}. Leave blank to remove the scheduled time."


class SeriesLengthForm(RevisionForm):
    series_length = forms.IntegerField(
        label="Games per match (best of)",
        required=False,
        min_value=1,
        help_text="Use an odd number. Leave blank to use the stage or round default.",
    )

    def __init__(self, *args, mode="BEST_OF", **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        if mode == "FIXED_GAMES":
            self.fields["series_length"].label = "Fixed games per match"
            self.fields[
                "series_length"
            ].help_text = (
                "Use a positive number. Leave blank to use the inherited default."
            )

    def clean_series_length(self):
        value = self.cleaned_data["series_length"]
        if value is not None:
            _validate_series_length(self.mode, value)
        return value


class ProgressForm(RevisionForm):
    side_one_score = forms.IntegerField(min_value=0)
    side_two_score = forms.IntegerField(min_value=0)

    def __init__(self, *args, match=None, **kwargs):
        super().__init__(*args, **kwargs)
        if match:
            for slot in match.slots.all():
                field = "side_one_score" if slot.position == 1 else "side_two_score"
                self.fields[field].label = f"{slot_label(slot)} — game wins"
                self.fields[field].widget.attrs["max"] = (
                    match.effective_series_length
                    if match.effective_series_mode == "FIXED_GAMES"
                    else (match.effective_series_length + 1) // 2
                )


class ResultForm(ProgressForm):
    outcome = forms.ChoiceField(
        label="How was the match decided?",
        initial=Match.Outcome.PLAYED,
        choices=(
            (Match.Outcome.PLAYED, "Played — decide the winner from the scores"),
            (
                Match.Outcome.FORFEIT,
                "Forfeit — one entrant wins without finishing play",
            ),
            (Match.Outcome.DOUBLE_FORFEIT, "Double forfeit — neither entrant advances"),
        ),
    )
    side_one_score = forms.IntegerField(required=False, min_value=0)
    side_two_score = forms.IntegerField(required=False, min_value=0)
    winner_position = forms.TypedChoiceField(
        label="Winner (for a forfeit only)",
        required=False,
        coerce=int,
        empty_value=None,
        choices=(("", "Choose the forfeit winner"), (1, "Side 1"), (2, "Side 2")),
        help_text="For a played match, the scores above determine the winner automatically.",
    )

    def __init__(self, *args, match=None, **kwargs):
        super().__init__(*args, match=match, **kwargs)
        if match:
            self.fields["winner_position"].choices = [
                ("", "Choose the forfeit winner")
            ] + [(slot.position, slot_label(slot)) for slot in match.slots.all()]
        self.order_fields(
            ("outcome", "side_one_score", "side_two_score", "winner_position")
        )


class CorrectionReasonForm(forms.Form):
    internal_reason = forms.CharField(
        label="Reason for correction",
        widget=forms.Textarea(attrs={"rows": 3}),
        min_length=1,
        help_text="Only authorized organizers can see this note.",
    )
