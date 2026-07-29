from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Institution
from .serializers import (
    AccountRegistrationSerializer,
    CurrentUserSerializer,
    InstitutionSerializer,
)


class InstitutionSearchView(generics.ListAPIView):
    serializer_class = InstitutionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        return (
            Institution.objects.filter(source=Institution.Source.CATALOGUE)
            .filter(
                Q(label__icontains=query)
                | Q(code__icontains=query)
                | Q(short_name__icontains=query)
                | Q(english_name__icontains=query)
                | Q(location__icontains=query)
            )
            .order_by("label")[:20]
        )


class AccountRegistrationView(generics.CreateAPIView):
    serializer_class = AccountRegistrationSerializer
    permission_classes = [AllowAny]


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
