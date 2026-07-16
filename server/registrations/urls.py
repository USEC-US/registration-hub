from rest_framework.routers import SimpleRouter

from .views import RegistrationViewSet

router = SimpleRouter()
router.register("registrations", RegistrationViewSet, basename="registration")

urlpatterns = router.urls
