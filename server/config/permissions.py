from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


class DebugOrStaffSchemaPermission(BasePermission):
    message = "API documentation is available to staff accounts."

    def has_permission(self, request, view) -> bool:
        if settings.DEBUG:
            return True
        if request.user and request.user.is_authenticated and request.user.is_staff:
            return True
        raise PermissionDenied(self.message)
