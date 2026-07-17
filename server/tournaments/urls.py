from rest_framework.routers import SimpleRouter

from .views import PublicTournamentViewSet

router = SimpleRouter()
router.register("tournaments", PublicTournamentViewSet, basename="public-tournament")

urlpatterns = router.urls
