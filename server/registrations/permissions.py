from rest_framework.permissions import BasePermission


class IsRegistrationSubmitter(BasePermission):
    message = "You can only access registrations you submitted."

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.submitted_by_id == request.user.id
