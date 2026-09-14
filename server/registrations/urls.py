from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import RegistrationViewSet, PaymentReferenceView

router = SimpleRouter()
router.register("registrations", RegistrationViewSet, basename="registration")

urlpatterns = [
    path("payment-references/", PaymentReferenceView.as_view())
] + router.urls
