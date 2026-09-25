from django import forms

from registrations.models import Registration

from .models import CompetitionEntrant, Match


class RevisionForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class CompetitionSetupForm(RevisionForm):
    name = forms.CharField(max_length=100, initial="Final bracket")
    default_series_length = forms.IntegerField(min_value=1, initial=3)

    def clean_default_series_length(self):
        value = self.cleaned_data["default_series_length"]
        if value % 2 == 0:
            raise forms.ValidationError("Best-of length must be odd.")
        return value


class EntrantSelectionForm(RevisionForm):
    registrations = forms.ModelMultipleChoiceField(
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
            .prefetch_related("members")
            .order_by("team_name", "pk")
        )


class DrawForm(RevisionForm):
    randomize = forms.BooleanField(required=False)

    def __init__(self, *args, competition, **kwargs):
        super().__init__(*args, **kwargs)
        self.entrants = list(
            CompetitionEntrant.objects.filter(competition=competition).order_by("pk")
        )
        choices = [(entrant.pk, str(entrant)) for entrant in self.entrants]
        for seed in range(1, len(self.entrants) + 1):
            self.fields[f"seed_{seed}"] = forms.ChoiceField(
                label=f"Seed {seed}", choices=choices, initial=choices[seed - 1][0]
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
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )


class SeriesLengthForm(RevisionForm):
    series_length = forms.IntegerField(required=False, min_value=1)

    def clean_series_length(self):
        value = self.cleaned_data["series_length"]
        if value is not None and value % 2 == 0:
            raise forms.ValidationError("Best-of length must be odd.")
        return value


class ProgressForm(RevisionForm):
    side_one_score = forms.IntegerField(min_value=0)
    side_two_score = forms.IntegerField(min_value=0)


class ResultForm(RevisionForm):
    outcome = forms.ChoiceField(
        choices=(
            (Match.Outcome.PLAYED, "Played"),
            (Match.Outcome.FORFEIT, "Forfeit"),
            (Match.Outcome.DOUBLE_FORFEIT, "Double forfeit"),
        )
    )
    side_one_score = forms.IntegerField(required=False, min_value=0)
    side_two_score = forms.IntegerField(required=False, min_value=0)
    winner_position = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=None,
        choices=((1, "Side 1"), (2, "Side 2")),
        help_text="Required for a forfeit; ignored for a played score.",
    )


class CorrectionReasonForm(forms.Form):
    internal_reason = forms.CharField(widget=forms.Textarea, min_length=1)
