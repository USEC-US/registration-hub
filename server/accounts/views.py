from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from .serializers import AccountRegistrationSerializer, CurrentUserSerializer


class AccountRegistrationView(generics.CreateAPIView):
    serializer_class = AccountRegistrationSerializer
    permission_classes = [AllowAny]


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
