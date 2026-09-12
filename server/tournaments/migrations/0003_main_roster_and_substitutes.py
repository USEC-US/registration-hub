import django.core.validators
from django.db import migrations, models


def split_limits(apps, schema_editor):
    game = apps.get_model("tournaments", "TournamentGame")
    game.objects.using(schema_editor.connection.alias).update(
        substitute_limit=models.F("substitute_limit") - models.F("main_roster_size")
    )


def combine_limits(apps, schema_editor):
    game = apps.get_model("tournaments", "TournamentGame")
    game.objects.using(schema_editor.connection.alias).update(
        substitute_limit=models.F("substitute_limit") + models.F("main_roster_size")
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0002_tournament_cover_image_tournament_is_featured")
    ]

    operations = [
        migrations.RemoveConstraint(
            "tournamentgame", "tournament_game_min_team_size_positive"
        ),
        migrations.RemoveConstraint(
            "tournamentgame", "tournament_game_max_team_size_at_least_min"
        ),
        migrations.RenameField("tournamentgame", "team_size_min", "main_roster_size"),
        migrations.RenameField("tournamentgame", "team_size_max", "substitute_limit"),
        migrations.RunPython(split_limits, combine_limits),
        migrations.AlterField(
            "tournamentgame",
            "main_roster_size",
            models.PositiveSmallIntegerField(
                "main roster size",
                validators=[django.core.validators.MinValueValidator(1)],
                help_text="Required number of main players per registration.",
            ),
        ),
        migrations.AlterField(
            "tournamentgame",
            "substitute_limit",
            models.PositiveSmallIntegerField(
                "maximum substitutes",
                default=0,
                help_text="Optional substitute places; zero means no substitutes.",
            ),
        ),
        migrations.AddConstraint(
            "tournamentgame",
            models.CheckConstraint(
                condition=models.Q(main_roster_size__gte=1),
                name="tournament_game_main_roster_positive",
            ),
        ),
        migrations.AddConstraint(
            "tournamentgame",
            models.CheckConstraint(
                condition=models.Q(substitute_limit__gte=0),
                name="tournament_game_substitute_limit_non_negative",
            ),
        ),
    ]
