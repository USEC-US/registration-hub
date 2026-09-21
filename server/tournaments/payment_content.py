"""Staff-authored bank transfer instructions, independent of payment references."""

import unicodedata
from string import Formatter

from django.core.exceptions import ValidationError

DEFAULT_TRANSFER_TEMPLATE = "{participant} thanh toan le phi {tournament_name}"


def normalize_transfer_content(value):
    value = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    return " ".join(
        "".join(c for c in value if not unicodedata.category(c).startswith("M")).split()
    )


def validate_transfer_template(value):
    try:
        for _, field, spec, conversion in Formatter().parse(value):
            if field is not None and (
                field not in {"participant", "tournament_name"} or spec or conversion
            ):
                raise ValueError
    except ValueError as error:
        raise ValidationError(
            "Use only {participant} and {tournament_name} placeholders."
        ) from error
    if not normalize_transfer_content(value):
        raise ValidationError("Enter transfer instructions.")


def snapshot_transfer_template(template, tournament_name):
    validate_transfer_template(template)

    # Escape literal braces so the remaining participant placeholder can be filled later.
    def escape(value):
        return value.replace("{", "{{").replace("}", "}}")

    return "".join(
        escape(literal)
        + (
            "{participant}"
            if field == "participant"
            else escape(tournament_name)
            if field
            else ""
        )
        for literal, field, _, _ in Formatter().parse(template)
    )


def render_transfer_content(template, participant, limit):
    try:
        needs_participant = any(
            field == "participant" for _, field, _, _ in Formatter().parse(template)
        )
        content = normalize_transfer_content(template.format(participant=participant))
    except (KeyError, ValueError, IndexError) as error:
        raise ValidationError(
            {
                "transfer_content": "Invalid transfer instructions. Contact the organizers."
            }
        ) from error
    if not content or (
        needs_participant and not normalize_transfer_content(participant)
    ):
        raise ValidationError(
            {"transfer_content": "Enter the team tag or player's in-game name first."}
        )
    if len(content) > limit:
        raise ValidationError(
            {
                "transfer_content": f"Transfer content exceeds {limit} characters. Contact the organizers for shorter instructions."
            }
        )
    return content
