from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.turnstile import require_turnstile

from .models import Registration
from .permissions import IsRegistrationSubmitter
from .serializers import (
    PaymentAttemptReceiptSerializer,
    PaymentAttemptSubmissionSerializer,
    RegistrationReadSerializer,
    RegistrationSubmissionSerializer,
)
from .services import submit_payment_attempt, submit_registration


def _as_drf_validation_error(error: DjangoValidationError) -> DRFValidationError:
    if hasattr(error, "error_dict"):
        return DRFValidationError(error.message_dict)
    return DRFValidationError(error.messages)


class RegistrationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsRegistrationSubmitter]
    serializer_class = RegistrationReadSerializer
    queryset = Registration.objects.none()

    def get_queryset(self):
        return (
            Registration.objects.filter(
                submitted_by=self.request.user,
                tournament_game__tournament__is_published=True,
            )
            .select_related("tournament_game__tournament", "tournament_game__game")
            .prefetch_related("members", "status_events", "payment_attempts")
        )

    @action(detail=False, methods=["post"], url_path="submit")
    def submit(self, request):
        serializer = RegistrationSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        require_turnstile(
            request,
            token=serializer.validated_data.get("turnstile_token", ""),
            expected_action="registration-submit",
        )
        try:
            registration = submit_registration(
                submitted_by=request.user,
                tournament_game_id=serializer.validated_data["tournament_game"].pk,
                team_name=serializer.validated_data["team_name"],
                members=serializer.to_member_inputs(),
            )
        except DjangoValidationError as error:
            raise _as_drf_validation_error(error) from error
        return Response(
            RegistrationReadSerializer(
                registration, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="payment-attempts")
    def payment_attempts(self, request, pk=None):
        registration = self.get_object()
        serializer = PaymentAttemptSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        require_turnstile(
            request,
            token=serializer.validated_data.pop("turnstile_token", ""),
            expected_action="payment-proof-submit",
        )
        try:
            payment_attempt = submit_payment_attempt(
                actor=request.user,
                registration_id=registration.pk,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            raise _as_drf_validation_error(error) from error
        return Response(
            PaymentAttemptReceiptSerializer(payment_attempt).data,
            status=status.HTTP_201_CREATED,
        )
