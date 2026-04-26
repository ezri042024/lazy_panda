from django.db import transaction
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from finance.defaults import create_default_finance_setup
from .serializers import RegisterSerializer, CurrentUserSerializer


class RegisterAPIView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        create_default_finance_setup(user)

        refresh = RefreshToken.for_user(user)

        user_data = CurrentUserSerializer(user).data

        return Response({
            "user": user_data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=201)


class CurrentUserAPIView(generics.RetrieveAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user