import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication

from config.turnstile import require_turnstile

from .models import PaymentAttempt, Registration
from .payments import (
    reserve_payment_reference,
    create_payment_intent,
    LegacyPaymentSessionError,
)
from django.db import transaction
from .permissions import IsRegistrationSubmitter
from .serializers import (
    PaymentCodeReadSerializer,
    PaymentInstructionsReadSerializer,
    PaymentReferenceRequestSerializer,
    PaymentReferenceReadSerializer,
    PaymentAttemptReceiptSerializer,
    PaymentAttemptSubmissionSerializer,
    RegistrationReadSerializer,
    RegistrationSubmissionSerializer,
)
from .services import submit_payment_attempt, submit_registration


@extend_schema(exclude=True)
class PaymentProofView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, path):
        attempts = PaymentAttempt.objects.all()
        user = request.user
        organizer = user.is_superuser or (
            user.is_staff
            and user.groups.filter(name="Organizers").exists()
            and user.has_perm("registrations.view_paymentattempt")
        )
        if not organizer:
            attempts = attempts.filter(registration__submitted_by=user)
        attempt = get_object_or_404(attempts, proof_file=f"payment-proofs/{path}")
        try:
            proof = attempt.proof_file.open("rb")
        except FileNotFoundError as error:
            raise Http404 from error
        response = FileResponse(proof, as_attachment=True)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


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
            .select_related(
                "tournament_game__tournament", "tournament_game__game", "payment_intent"
            )
            .prefetch_related("members", "status_events", "payment_attempts")
        )

    @action(
        detail=False, methods=["post"], url_path="submit", permission_classes=[AllowAny]
    )
    def submit(self, request):
        payload = request.data
        proof_file = None
        reference = ""
        if request.content_type.startswith("multipart/"):
            unknown = set(request.data) - {"payload", "proof_file", "reference"}
            if unknown:
                raise DRFValidationError(
                    {field: "This field is not allowed." for field in unknown}
                )
            try:
                payload = json.loads(request.data.get("payload", ""))
            except (TypeError, ValueError) as error:
                raise DRFValidationError(
                    {"payload": "Provide valid registration JSON."}
                ) from error
            proof_file = request.FILES.get("proof_file")
            reference = request.data.get("reference", "")
            if len(reference) > 128:
                raise DRFValidationError(
                    {"reference": "Maximum length is 128 characters."}
                )
        serializer = RegistrationSubmissionSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        require_turnstile(
            request,
            token=serializer.validated_data.get("turnstile_token", ""),
            expected_action="registration-submit",
        )
        try:
            registration = submit_registration(
                submitted_by=request.user if request.user.is_authenticated else None,
                proof_file=proof_file,
                reference=reference,
                **{
                    key: value
                    for key, value in serializer.validated_data.items()
                    if key
                    not in {
                        "tournament_game",
                        "team_name",
                        "members",
                        "turnstile_token",
                    }
                },
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

    @extend_schema(request=None, responses=PaymentCodeReadSerializer)
    @action(detail=True, methods=["post"], url_path="payment-reference")
    def payment_reference(self, request, pk=None):
        registration = self.get_object()
        with transaction.atomic():
            registration = Registration.objects.select_for_update().get(
                pk=registration.pk
            )
            try:
                intent = registration.payment_intent
            except Registration.payment_intent.RelatedObjectDoesNotExist:
                try:
                    intent = create_payment_intent(
                        tournament_game=registration.tournament_game,
                        registration=registration,
                    )
                except DjangoValidationError as error:
                    raise _as_drf_validation_error(error) from error
        return Response({"reference": intent.reference})

    @extend_schema(request=None, responses=PaymentInstructionsReadSerializer)
    @action(detail=True, methods=["post"], url_path="payment-instructions")
    def payment_instructions(self, request, pk=None):
        registration = self.get_object()
        with transaction.atomic():
            registration = Registration.objects.select_for_update().get(
                pk=registration.pk
            )
            try:
                intent = registration.payment_intent
            except Registration.payment_intent.RelatedObjectDoesNotExist:
                try:
                    intent = create_payment_intent(
                        tournament_game=registration.tournament_game,
                        registration=registration,
                    )
                except DjangoValidationError as error:
                    raise _as_drf_validation_error(error) from error
        response = Response(PaymentInstructionsReadSerializer(intent).data)
        response["Cache-Control"] = "private, no-store"
        return response

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


class PaymentReferenceThrottle(SimpleRateThrottle):
    rate = "30/hour"
    scope = "payment-reference"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PaymentReferenceView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PaymentReferenceThrottle]

    @extend_schema(
        request=PaymentReferenceRequestSerializer,
        responses=PaymentReferenceReadSerializer,
    )
    def post(self, request):
        serializer = PaymentReferenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            intent = reserve_payment_reference(
                tournament_game_id=serializer.validated_data["tournament_game"].pk,
                token=serializer.validated_data.get("token"),
            )
        except LegacyPaymentSessionError as error:
            return Response(
                {**error.message_dict, "code": "legacy_payment_session"},
                status=status.HTTP_400_BAD_REQUEST,
                headers={"Cache-Control": "private, no-store"},
            )
        except DjangoValidationError as error:
            raise _as_drf_validation_error(error) from error
        response = Response(PaymentReferenceReadSerializer(intent).data)
        response["Cache-Control"] = "private, no-store"
        return response
