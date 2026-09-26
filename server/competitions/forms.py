from django import forms
from django.utils import timezone

from registrations.models import Registration
from tournaments.models import TournamentGame

from .admin_workspace import slot_label
from .commands import _entrant_label
from .models import CompetitionEntrant, Match, StageDraw


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
    default_series_length = forms.IntegerField(
        label="Games per match (best of)",
        min_value=1,
        initial=3,
        help_text="Use 1, 3, 5, … For best of 3, the first to 2 game wins advances.",
    )

    def clean_default_series_length(self):
        value = self.cleaned_data["default_series_length"]
        if value % 2 == 0:
            raise forms.ValidationError("Best-of length must be odd.")
        return value


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
            CompetitionEntrant.objects.filter(competition=competition).order_by("pk")
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

    def clean_series_length(self):
        value = self.cleaned_data["series_length"]
        if value is not None and value % 2 == 0:
            raise forms.ValidationError("Best-of length must be odd.")
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
                    match.effective_series_length + 1
                ) // 2


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
