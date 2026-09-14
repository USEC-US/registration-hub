from rest_framework.permissions import BasePermission


class IsRegistrationSubmitter(BasePermission):
    message = "You can only access registrations you submitted."

    def has_object_permission(self, request, view, obj) -> bool:
        return (
            request.user.is_authenticated
            and request.user.pk is not None
            and obj.submitted_by_id == request.user.pk
        )


def resolve_private_registration(request, registration_id):
    """A supplied credential must succeed; it never falls through to JWT authority."""
    from django.http import Http404
    from .access import resolve_registration_access
    from .models import Registration

    if "X-Registration-Access" in request.headers:
        access = resolve_registration_access(
            request.headers["X-Registration-Access"], registration_id=registration_id
        )
        return access.registration, access
    if request.user.is_authenticated and request.user.pk is not None:
        try:
            return Registration.objects.get(
                pk=registration_id, submitted_by_id=request.user.pk
            ), None
        except Registration.DoesNotExist:
            pass
    raise Http404("Saved registration not found.")
