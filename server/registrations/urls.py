from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import RegistrationViewSet, PaymentReferenceView

from .private_views import (
    RegistrationResumeView,
    RegistrationPaymentSessionView,
    RegistrationPaymentProofView,
)

router = SimpleRouter()
router.register("registrations", RegistrationViewSet, basename="registration")

urlpatterns = [
    path("registrations/resume/", RegistrationResumeView.as_view()),
    path(
        "registrations/<int:pk>/payment-session/",
        RegistrationPaymentSessionView.as_view(),
    ),
    path(
        "registrations/<int:pk>/payment-proof/", RegistrationPaymentProofView.as_view()
    ),
    path("payment-references/", PaymentReferenceView.as_view()),
] + router.urls
