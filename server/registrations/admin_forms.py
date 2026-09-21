from django import forms
from unfold.widgets import UnfoldAdminSelect2Widget

from .models import Bank, PaymentSettings


class PaymentSettingsForm(forms.ModelForm):
    bank_bin = forms.ChoiceField(
        label="Bank",
        required=False,
        widget=UnfoldAdminSelect2Widget,
        help_text="Search by bank name, code, or BIN. Saving fills the bank name and BIN automatically.",
    )
    bank_name = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = PaymentSettings
        fields = (
            "enabled",
            "bank_bin",
            "bank_name",
            "account_number",
            "account_holder",
            "payment_hold_minutes",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.banks = {bank.bin: bank for bank in Bank.objects.filter(is_active=True)}
        self.saved_bin = self.instance.bank_bin
        self.saved_name = self.instance.bank_name
        choices = [("", "Choose a bank")]
        choices.extend((bin_code, str(bank)) for bin_code, bank in self.banks.items())
        if self.saved_bin and self.saved_bin not in self.banks:
            choices.append(
                (self.saved_bin, f"{self.saved_name} — {self.saved_bin} (saved bank)")
            )
        self.fields["bank_bin"].choices = choices
        if not self.banks:
            self.fields["bank_bin"].help_text = (
                "The catalogue is empty. Open Banks and refresh the catalogue. "
                "An existing saved bank remains available."
            )

    def clean(self):
        cleaned = super().clean()
        bin_code = cleaned.get("bank_bin", "")
        bank = self.banks.get(bin_code)
        # Never trust a posted display name; derive both details from the chosen bank.
        cleaned["bank_name"] = (
            bank.short_name
            if bank
            else self.saved_name
            if bin_code == self.saved_bin
            else ""
        )
        return cleaned
