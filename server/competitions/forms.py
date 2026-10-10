from django import forms
from django.utils import timezone

from registrations.models import Registration
from tournaments.models import TournamentGame

from .admin_workspace import slot_label
from .commands import _entrant_label
from .models import CompetitionEntrant, Match, Stage, StageDraw, TieResolution
from .command_support import MAX_ENTRANTS, _validate_series_length
from .round_robin import DEFAULT_TIEBREAKS
from .round_robin_commands import group_standings
from .swiss import DEFAULT_TIEBREAKS as SWISS_DEFAULT_TIEBREAKS

TIEBREAK_CHOICES = (
    ("", "No rule"),
    ("HEAD_TO_HEAD", "Head-to-head points"),
    ("OPPONENT_POINTS", "Opponent points"),
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
    stage_sequence = forms.IntegerField(
        min_value=1,
        max_value=32767,
        required=False,
        widget=forms.HiddenInput,
        initial=1,
        disabled=True,
    )
    name = forms.CharField(label="Stage name", max_length=100, initial="Final bracket")
    format = forms.ChoiceField(
        required=False,
        choices=(
            (Stage.Format.SINGLE_ELIMINATION, "Single elimination"),
            (Stage.Format.DOUBLE_ELIMINATION, "Double elimination"),
            (Stage.Format.ROUND_ROBIN, "Round robin"),
            (Stage.Format.SWISS_FIXED, "Fixed Swiss"),
            (Stage.Format.SWISS_THRESHOLD, "Threshold Swiss"),
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

    round_policy = forms.ChoiceField(
        label="Round policy",
        required=False,
        choices=(("AUTOMATIC", "Recommended rounds"), ("CUSTOM", "Custom rounds")),
        initial="AUTOMATIC",
    )
    round_count = forms.IntegerField(
        label="Custom rounds", required=False, min_value=1, max_value=64
    )
    win_target = forms.IntegerField(
        label="Wins to qualify", required=False, min_value=1, max_value=64
    )
    loss_limit = forms.IntegerField(
        label="Losses to eliminate", required=False, min_value=1, max_value=64
    )

    def __init__(
        self, *args, incoming_count=None, is_final=True, group_plans=(), **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.incoming_count = incoming_count
        self.is_final = is_final
        values = self.data if self.is_bound else self.initial
        format_ = values.get("format", Stage.Format.SINGLE_ELIMINATION)
        swiss = format_ in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)
        self.recommended_rounds = (
            (incoming_count - 1).bit_length() if incoming_count else None
        )
        self.fields["round_policy"].help_text = (
            f"Recommended rounds: {self.recommended_rounds}. This does not guarantee distinct final positions."
            if incoming_count
            else "Pending ceil(log2(actual N)); the actual incoming field resolves this saved automatic policy."
        )
        if not self.is_bound:
            if self.initial.get("round_count") is None:
                self.initial["round_count"] = self.recommended_rounds
        defaults = SWISS_DEFAULT_TIEBREAKS if swiss else DEFAULT_TIEBREAKS
        for index in range(1, 5):
            self.fields[f"tiebreak_{index}"] = forms.ChoiceField(
                label=f"Tiebreaker {index}",
                required=False,
                choices=TIEBREAK_CHOICES,
                initial=defaults[index - 1] if index <= 3 else "",
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
        if swiss:
            self.fields[
                "tiebreak_1"
            ].help_text = "Opponent points sums current ordinary-round opponents' points. Byes have no opponent."
        self.setup_fields = [
            self[name]
            for name in self.fields
            if name != "expected_revision" and name != "stage_sequence"
        ]
        limit = incoming_count or MAX_ENTRANTS
        grouped = (self.data if self.is_bound else self.initial).get(
            "format"
        ) == "ROUND_ROBIN"
        self.fields["advancement_count"] = forms.TypedChoiceField(
            label="Entrants advancing to the next stage",
            coerce=int,
            empty_value=None,
            required=(
                format_ == Stage.Format.SWISS_FIXED
                or (not is_final and not grouped and not swiss)
            ),
            choices=[
                ("", "None (final stage)"),
                *(
                    (n, f"Top {n}")
                    for n in range(
                        2 if format_ == Stage.Format.SWISS_FIXED else 1, limit + 1
                    )
                ),
            ],
            help_text="Choose how many qualify. Leave empty for the final stage. Cutoff ties require Extra Matches or Manual Decision.",
            disabled=self.is_bound
            and (grouped or format_ == Stage.Format.SWISS_THRESHOLD),
        )
        if format_ == Stage.Format.SWISS_FIXED:
            self.fields["advancement_count"].label = "Top-N qualifying places"
            self.fields[
                "advancement_count"
            ].help_text = "Choose 2 through the actual field size. Complete every ordinary round and cutoff decision before handoff."
        automatic_groups = (
            values.get(
                "group_size_policy",
                "EXACT"
                if self.is_bound
                else "AUTOMATIC"
                if (group_plans and group_plans[0].size is None) or not incoming_count
                else "EXACT",
            )
            == "AUTOMATIC"
        )
        self.fields["group_size_policy"] = forms.ChoiceField(
            label="Group sizes",
            required=False,
            choices=(
                ("EXACT", "Exact sizes"),
                ("AUTOMATIC", "Automatic sizes from the actual field"),
            ),
            initial="AUTOMATIC" if automatic_groups else "EXACT",
            disabled=self.is_bound and not grouped,
            help_text="Automatic sizes fill each quota, then balance the remaining entrants. Locked quotas never change.",
        )
        self.fields["group_count"] = forms.TypedChoiceField(
            label="Number of groups",
            coerce=int,
            required=grouped,
            choices=[(n, n) for n in range(1, limit // 2 + 1)],
            initial=len(group_plans) or 1,
            disabled=self.is_bound and not grouped,
        )
        raw_count = (
            self.data.get("group_count", 1) if self.is_bound else len(group_plans) or 1
        )
        try:
            count = int(raw_count)
        except (ValueError, TypeError):
            count = 1
        if not 1 <= count <= limit // 2:
            count = 1
        self.group_rows = []
        for index in range(1, count + 1):
            plan = group_plans[index - 1] if index <= len(group_plans) else None
            self.fields[f"group_name_{index}"] = forms.CharField(
                label=f"Group {index} name",
                max_length=100,
                required=grouped,
                initial=plan.name if plan else f"Group {index}",
                disabled=self.is_bound and not grouped,
            )
            self.fields[f"group_size_{index}"] = forms.TypedChoiceField(
                label=f"Group {index} entrants",
                coerce=int,
                required=grouped and not automatic_groups,
                choices=[("", "Automatic"), *((n, n) for n in range(2, limit + 1))],
                initial=None
                if automatic_groups
                else plan.size
                if plan
                else (limit // count + (index <= limit % count))
                if incoming_count
                else 2,
                disabled=self.is_bound and (not grouped or automatic_groups),
                empty_value=None,
            )
            self.fields[f"group_quota_{index}"] = forms.TypedChoiceField(
                label=f"Group {index} qualifiers",
                coerce=int,
                required=grouped,
                choices=[(n, n) for n in range(1, limit + 1)],
                initial=plan.qualifying_places if plan else 1,
                disabled=self.is_bound and not grouped,
            )
            self.group_rows.append(
                [self[f"group_{part}_{index}"] for part in ("name", "size", "quota")]
            )
        for name in ("round_policy", "round_count", "win_target", "loss_limit"):
            enabled = (
                name in ("win_target", "loss_limit")
                and format_ == Stage.Format.SWISS_THRESHOLD
            ) or (
                name in ("round_policy", "round_count")
                and format_ == Stage.Format.SWISS_FIXED
            )
            if name == "round_count" and values.get("round_policy") != "CUSTOM":
                enabled = False
            self.fields[name].disabled = self.is_bound and not enabled
        # Disabled fields still validate initial values, which may contain stale rules.
        for name, field in self.fields.items():
            if self.is_bound and field.disabled and name != "stage_sequence":
                self.initial[name] = None

    def clean(self):
        cleaned = super().clean()
        format_ = cleaned.get("format") or Stage.Format.SINGLE_ELIMINATION
        if format_ == Stage.Format.ROUND_ROBIN:
            cleaned["group_size_policy"] = cleaned.get("group_size_policy") or "EXACT"
        policy = cleaned.get("grand_final_policy", "")
        cleaned["format"] = format_
        mode = (
            (cleaned.get("series_mode") or "BEST_OF")
            if format_ in ("ROUND_ROBIN", "SWISS_FIXED")
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
        if format_ in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD):
            for field in ("win_points", "draw_points", "loss_points"):
                if cleaned.get(field) is None:
                    self.add_error(field, "Enter the points for this result.")
            if format_ == Stage.Format.SWISS_FIXED:
                if (
                    cleaned.get("round_policy") == "CUSTOM"
                    and cleaned.get("round_count") is None
                ):
                    self.add_error("round_count", "Enter your custom round count.")
                if cleaned.get("round_policy") != "CUSTOM":
                    cleaned["round_count"] = None
                cleaned["win_target"] = cleaned["loss_limit"] = None
            else:
                cleaned["round_count"] = cleaned["advancement_count"] = None
                for field in ("win_target", "loss_limit"):
                    if cleaned.get(field) is None:
                        self.add_error(field, "Enter a positive target.")
        if format_ == "ROUND_ROBIN":
            for field in ("win_points", "draw_points", "loss_points"):
                if cleaned.get(field) is None:
                    self.add_error(field, "Enter the points for this result.")
            specs = []
            names = set()
            for index in range(1, len(self.group_rows) + 1):
                name = cleaned.get(f"group_name_{index}")
                size = cleaned.get(f"group_size_{index}")
                quota = cleaned.get(f"group_quota_{index}")
                if name in names:
                    self.add_error(f"group_name_{index}", "Use a unique group name.")
                names.add(name)
                if size and quota and quota > size:
                    self.add_error(
                        f"group_quota_{index}", "The quota cannot exceed group size."
                    )
                if (
                    name
                    and quota
                    and (size or cleaned.get("group_size_policy") == "AUTOMATIC")
                ):
                    specs.append((name, size, quota))
            if len(specs) == len(self.group_rows):
                total = sum(
                    size if size is not None else max(2, quota)
                    for _, size, quota in specs
                )
                if (
                    cleaned.get("group_size_policy") != "AUTOMATIC"
                    and self.incoming_count
                    and total != self.incoming_count
                ):
                    self.add_error(
                        "group_count",
                        f"Group sizes must total the incoming field of {self.incoming_count}; they total {total}.",
                    )
                elif total > MAX_ENTRANTS:
                    self.add_error(
                        "group_count",
                        "Group sizes cannot total more than 256 entrants.",
                    )
            cleaned["group_specs"] = specs
        elif (
            not self.is_final
            and format_ not in (Stage.Format.SWISS_FIXED, Stage.Format.SWISS_THRESHOLD)
            and cleaned.get("advancement_count") is None
            and "advancement_count" not in self.errors
        ):
            self.add_error("advancement_count", "Choose how many entrants advance.")
        if format_ == Stage.Format.DOUBLE_ELIMINATION and not policy:
            self.add_error("grand_final_policy", "Choose reset or no reset.")
        elif format_ == Stage.Format.SINGLE_ELIMINATION and policy:
            self.add_error(
                "grand_final_policy", "Single elimination has no final policy."
            )
        return cleaned


class SwissRoundForm(RevisionForm):
    regenerate = forms.BooleanField(
        label="Regenerate the private preview",
        required=False,
        help_text="Explicitly replace an outdated private preview. Earlier previews remain historical.",
    )


class SwissRematchForm(RevisionForm):
    confirm_rematches = forms.BooleanField(
        label="I confirm required rematches for this round"
    )
    internal_reason = forms.CharField(
        label="Private organizer reason",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Explain the exception. Only authorized organizers can see this note.",
    )


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
        self.group_plans = list(stage.group_plans.all()) if stage else []
        choices = [(p.number, p.name) for p in self.group_plans]
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
        specs = [(p.name, p.qualifying_places) for p in self.group_plans]
        if not specs:
            self.add_error(
                None, "Configure groups in Stage Add/Edit before saving the draw."
            )
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


class QualificationTieForm(RevisionForm):
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

    def __init__(self, *args, group=None, draw=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .qualification import stage_qualification

        draw = group.draw if group else draw
        state = (
            group_standings(group)
            if group
            else {"cutoff_ties": stage_qualification(draw)["cutoffs"]}
        )
        self.tie = next(
            (tie for tie in state["cutoff_ties"] if tie["resolution_id"] is None), None
        )
        entries = {
            entry.pk: entry.entrant.display_name
            for entry in draw.entries.select_related("entrant")
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
                "This stage has no qualification tie awaiting a choice."
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


GroupTieForm = QualificationTieForm


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


class StageOrderForm(RevisionForm):
    def __init__(self, *args, competition, **kwargs):
        super().__init__(*args, **kwargs)
        self.stages = list(competition.stages.all())
        choices = [(s.pk, s.name) for s in self.stages]
        for i, stage in enumerate(self.stages, 1):
            self.fields[f"position_{i}"] = forms.TypedChoiceField(
                label=f"Stage {i}", choices=choices, coerce=int, initial=stage.pk
            )

    def clean(self):
        data = super().clean()
        data["stage_ids"] = [
            data.get(f"position_{i}") for i in range(1, len(self.stages) + 1)
        ]
        if len(set(data["stage_ids"])) != len(self.stages):
            raise forms.ValidationError("Include each stage exactly once.")
        return data


class NextStageDrawForm(RevisionForm):
    regenerate = forms.BooleanField(
        label="Replace the existing private preview with a new random draw",
        required=False,
    )
