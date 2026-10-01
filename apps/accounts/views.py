from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import BankAccount
from .serializers import (
    BankAccountSerializer,
    LoginSerializer,
    ProfileSerializer,
    RegisterSerializer,
    TokenPairSerializer,
)


class ThrottledAuthMixin:
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
    permission_classes = [AllowAny]
    authentication_classes: list = []


class RegisterView(ThrottledAuthMixin, APIView):
    @extend_schema(request=RegisterSerializer, responses={201: TokenPairSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({"refresh": str(refresh), "access": str(refresh.access_token)}, status=status.HTTP_201_CREATED)


class LoginView(ThrottledAuthMixin, APIView):
    @extend_schema(request=LoginSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user.profile


class BankAccountView(generics.GenericAPIView):
    serializer_class = BankAccountSerializer

    def get(self, request):
        account = BankAccount.objects.filter(user=request.user).first()
        if not account:
            return Response({"detail": "No bank account saved."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(account).data)

    def put(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Use save() (not update_or_create) so account_last4 is derived.
        account = BankAccount.objects.filter(user=request.user).first() or BankAccount(user=request.user)
        for key, value in serializer.validated_data.items():
            setattr(account, key, value)
        account.save()
        return Response(self.get_serializer(account).data)

    def delete(self, request):
        BankAccount.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
