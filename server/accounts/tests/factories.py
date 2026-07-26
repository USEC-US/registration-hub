from django.contrib.auth import get_user_model


def create_account(
    *,
    email: str = "player@example.com",
    password: str = "strong-password",
    first_name: str = "Test",
    last_name: str = "User",
    **extra_fields,
):
    return get_user_model().objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        **extra_fields,
    )
