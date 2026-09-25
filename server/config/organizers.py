from django.core.exceptions import PermissionDenied


def is_organizer_staff(user) -> bool:
    return bool(
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or (user.is_staff and user.groups.filter(name="Organizers").exists())
        )
    )


def require_organizer(user, permission: str) -> None:
    if is_organizer_staff(user) and (user.is_superuser or user.has_perm(permission)):
        return
    raise PermissionDenied("An Organizer staff account is required.")
