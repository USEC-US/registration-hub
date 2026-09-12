from django.db import migrations, models


def label_existing_members(apps, schema_editor):
    member = apps.get_model("registrations", "RegistrationMember")
    # The old form placed required slots first and optional players afterward.
    # Preserve the submitted captain, order, and identity/institution snapshots.
    member.objects.using(schema_editor.connection.alias).filter(
        display_order__gt=models.F("registration__tournament_game__main_roster_size")
    ).update(roster_role="substitute")


class Migration(migrations.Migration):
    dependencies = [
        ("registrations", "0002_registration_contact_discord_snapshot_and_more"),
        ("tournaments", "0003_main_roster_and_substitutes"),
    ]
    operations = [
        migrations.AddField(
            "registrationmember",
            "roster_role",
            models.CharField(
                choices=[("main", "Main player"), ("substitute", "Substitute")],
                default="main",
                max_length=10,
            ),
        ),
        migrations.RunPython(label_existing_members, migrations.RunPython.noop),
        migrations.AddConstraint(
            "registrationmember",
            models.CheckConstraint(
                condition=models.Q(roster_role__in=("main", "substitute")),
                name="registration_member_valid_roster_role",
            ),
        ),
    ]
