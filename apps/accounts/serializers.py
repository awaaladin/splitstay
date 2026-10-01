from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import BankAccount, Profile
from .phone import normalize_phone

User = get_user_model()


def validate_unique_phone(value, *, exclude_user=None):
    phone = normalize_phone(value)
    if not phone:
        return None
    qs = Profile.objects.filter(phone_number=phone)
    if exclude_user:
        qs = qs.exclude(user=exclude_user)
    if qs.exists():
        raise serializers.ValidationError("This phone number is already registered.")
    return phone


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    full_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate_phone_number(self, value):
        return validate_unique_phone(value)

    def validate(self, attrs):
        validate_password(attrs["password"])
        return attrs

    @transaction.atomic
    def create(self, validated):
        user = User.objects.create_user(email=validated["email"], password=validated["password"])
        profile = user.profile
        profile.full_name = validated["full_name"]
        profile.phone_number = validated.get("phone_number") or None
        profile.save()
        return user


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Email address or phone number")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"), username=attrs["identifier"], password=attrs["password"]
        )
        if user is None:
            raise serializers.ValidationError("Invalid credentials.", code="authorization")
        refresh = RefreshToken.for_user(user)
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class TokenPairSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()


class ProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = Profile
        fields = ("id", "email", "full_name", "phone_number", "avatar")

    def validate_phone_number(self, value):
        return validate_unique_phone(value, exclude_user=self.instance.user if self.instance else None)


class UserSummarySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "name")


class BankAccountSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(write_only=True, min_length=10, max_length=10)
    masked_number = serializers.CharField(read_only=True)

    class Meta:
        model = BankAccount
        fields = ("bank_code", "bank_name", "account_name", "account_number", "masked_number")

    def validate_account_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Account numbers are 10 digits.")
        return value
