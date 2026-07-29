from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import AccountRegistrationView, CurrentUserView, InstitutionSearchView

urlpatterns = [
    path("institutions/", InstitutionSearchView.as_view(), name="institution-search"),
    path("auth/register/", AccountRegistrationView.as_view(), name="account-register"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("account/me/", CurrentUserView.as_view(), name="account-me"),
]
