"""Saved guest access and owner JWT routes. Credentials never authorize listing."""

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.exceptions import ValidationError

from config.turnstile import require_turnstile
from .access import resolve_registration_access
from .payment_sessions import build_payment_session
from .permissions import resolve_private_registration
from .serializers import (
    PrivatePaymentProofSerializer,
    RegistrationPaymentSessionSerializer,
)
from .services import submit_payment_attempt


class PrivateResponseMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class PrivateRegistrationThrottle(SimpleRateThrottle):
    scope = "private-registration"
    rate = "120/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PrivateProofThrottle(PrivateRegistrationThrottle):
    scope = "private-payment-proof"
    rate = "30/hour"


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="X-Registration-Access",
            location=OpenApiParameter.HEADER,
            type=str,
            description="Exactly 64 lowercase hexadecimal characters. Required for resume or guest access; scoped owner routes also accept owner JWT.",
        )
    ]
)
class PrivateRegistrationView(PrivateResponseMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PrivateRegistrationThrottle]

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )
        return super().handle_exception(exc)


class RegistrationResumeView(PrivateRegistrationView):
    @extend_schema(request=None, responses=RegistrationPaymentSessionSerializer)
    def post(self, request):
        access = resolve_registration_access(
            request.headers.get("X-Registration-Access")
        )
        return Response(build_payment_session(access.registration))


class RegistrationPaymentSessionView(PrivateRegistrationView):
    @extend_schema(request=None, responses=RegistrationPaymentSessionSerializer)
    def post(self, request, pk):
        registration, _ = resolve_private_registration(request, pk)
        return Response(build_payment_session(registration))


class RegistrationPaymentProofView(PrivateRegistrationView):
    throttle_classes = [PrivateProofThrottle]

    @extend_schema(
        request=PrivatePaymentProofSerializer,
        responses=RegistrationPaymentSessionSerializer,
    )
    def post(self, request, pk):
        registration, access = resolve_private_registration(request, pk)
        serializer = PrivatePaymentProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        require_turnstile(
            request,
            token=serializer.validated_data.pop("turnstile_token", ""),
            expected_action="payment-proof-submit",
        )
        submit_payment_attempt(
            actor=request.user,
            registration_id=registration.pk,
            registration_access=access,
            amount=registration.fee_amount_snapshot,
            currency=registration.fee_currency_snapshot,
            **serializer.validated_data,
        )
        registration.refresh_from_db()
        return Response(build_payment_session(registration))
