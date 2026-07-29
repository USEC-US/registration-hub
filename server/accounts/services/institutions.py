from django.core.exceptions import ValidationError

from accounts.models import Institution


def normalize_institution_label(value: str) -> str:
    return " ".join(value.split()).casefold()


def resolve_institution(
    *, institution_id: int | None, institution_label: str | None
) -> Institution:
    has_institution_id = bool(institution_id)
    has_institution_label = bool(institution_label and institution_label.strip())
    if has_institution_id == has_institution_label:
        raise ValidationError("Choose a catalogue institution or enter a custom label.")

    if has_institution_id:
        return Institution.objects.get(
            pk=institution_id,
            source=Institution.Source.CATALOGUE,
        )

    label = " ".join(institution_label.split())
    normalized_label = normalize_institution_label(label)
    return Institution.objects.filter(
        source=Institution.Source.CATALOGUE,
        normalized_label=normalized_label,
    ).first() or Institution.objects.get_or_create(
        source=Institution.Source.CUSTOM,
        normalized_label=normalized_label,
        defaults={
            "label": label,
            "review_status": Institution.ReviewStatus.PENDING,
        },
    )[0]
