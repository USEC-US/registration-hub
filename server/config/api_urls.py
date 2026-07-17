from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.permissions import DebugOrStaffSchemaPermission

schema_view = SpectacularAPIView.as_view(
    permission_classes=[DebugOrStaffSchemaPermission]
)

urlpatterns = [
    path("", include("accounts.urls")),
    path("", include("registrations.urls")),
    path("schema/", schema_view, name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            permission_classes=[DebugOrStaffSchemaPermission],
        ),
        name="docs",
    ),
]
