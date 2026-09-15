from registrations.models import PaymentSettings


def configure_test_payments():
    """Explicit fictional receiving destination, only in disposable test databases."""
    return PaymentSettings.objects.update_or_create(
        pk=1,
        defaults=dict(
            enabled=True,
            bank_name="Test bank",
            bank_bin="970436",
            account_number="0000012345",
            account_holder="TEST ONLY",
            payment_hold_minutes=60,
        ),
    )[0]
