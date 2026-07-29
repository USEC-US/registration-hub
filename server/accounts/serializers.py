from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Institution
from .services.institutions import resolve_institution


class InstitutionSerializer(serializers.ModelSerializer):
    shortName = serializers.CharField(source="short_name")
    eng = serializers.CharField(source="english_name")

    class Meta:
        model = Institution
        fields = ("id", "value", "label", "code", "shortName", "eng", "type", "location")


class InstitutionChoiceSerializerMixin(serializers.Serializer):
    defer_institution_resolution = False
    institution = InstitutionSerializer(read_only=True)
    institution_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    institution_label = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=255,
    )

    def validate(self, attrs):
        has_institution_id = "institution_id" in attrs
        has_institution_label = "institution_label" in attrs
        if self.partial and not has_institution_id and not has_institution_label:
            return attrs

        institution_id = attrs.get("institution_id")
        institution_label = attrs.get("institution_label")
        try:
            if self.defer_institution_resolution:
                self._validate_institution_choice(
                    institution_id=institution_id,
                    institution_label=institution_label,
                )
            else:
                attrs["institution"] = resolve_institution(
                    institution_id=attrs.pop("institution_id", None),
                    institution_label=attrs.pop("institution_label", None),
                )
        except Institution.DoesNotExist as error:
            raise serializers.ValidationError(
                {"institution_id": "Select a valid catalogue institution."}
            ) from error
        except DjangoValidationError as error:
            raise serializers.ValidationError({"institution": error.messages}) from error
        return attrs

    def _validate_institution_choice(
        self,
        *,
        institution_id: int | None,
        institution_label: str | None,
    ) -> None:
        has_institution_id = bool(institution_id)
        has_institution_label = bool(institution_label and institution_label.strip())
        if has_institution_id == has_institution_label:
            raise DjangoValidationError(
                "Choose a catalogue institution or enter a custom label."
            )

        if has_institution_id:
            Institution.objects.get(
                pk=institution_id,
                source=Institution.Source.CATALOGUE,
            )


class AccountRegistrationSerializer(
    InstitutionChoiceSerializerMixin,
    serializers.ModelSerializer,
):
    defer_institution_resolution = True
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=True, max_length=150)
    turnstile_token = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "institution",
            "institution_id",
            "institution_label",
            "turnstile_token",
        )
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("turnstile_token", None)
        validated_data["institution"] = resolve_institution(
            institution_id=validated_data.pop("institution_id", None),
            institution_label=validated_data.pop("institution_label", None),
        )
        return get_user_model().objects.create_user(password=password, **validated_data)


class CurrentUserSerializer(InstitutionChoiceSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "institution",
            "institution_id",
            "institution_label",
        )
        read_only_fields = ("id", "email")
