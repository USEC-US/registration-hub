from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q


PERMISSION_SPEC = {
    "tournaments": {
        "game": ("add", "change", "view"),
        "tournament": ("add", "change", "view"),
        "tournamentgame": ("add", "change", "view"),
    },
    "registrations": {
        "registration": ("change", "view"),
        "registrationmember": ("view",),
        "paymentattempt": ("change", "view"),
        "registrationstatusevent": ("view",),
    },
}


class Command(BaseCommand):
    help = "Create or update the least-privilege Organizers group."

    def handle(self, *args, **options):
        permission_filter = Q(pk__in=[])
        required = set()
        for app_label, model_specs in PERMISSION_SPEC.items():
            for model_name, verbs in model_specs.items():
                codenames = {f"{verb}_{model_name}" for verb in verbs}
                required.update((app_label, codename) for codename in codenames)
                permission_filter |= Q(
                    content_type__app_label=app_label,
                    content_type__model=model_name,
                    codename__in=codenames,
                )

        permissions = Permission.objects.filter(permission_filter).select_related(
            "content_type"
        )
        found = {
            (permission.content_type.app_label, permission.codename)
            for permission in permissions
        }
        missing = required - found
        if missing:
            formatted = ", ".join(
                f"{app_label}.{codename}" for app_label, codename in sorted(missing)
            )
            raise CommandError(f"Required permissions are missing: {formatted}")

        group, _ = Group.objects.get_or_create(name="Organizers")
        group.permissions.set(permissions)
        self.stdout.write(self.style.SUCCESS("Organizers group is configured."))
