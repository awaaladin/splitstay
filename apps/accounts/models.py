from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from .fields import EncryptedTextField


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self):
        return self.email

    @property
    def display_name(self) -> str:
        profile = getattr(self, "profile", None)
        return profile.full_name if profile and profile.full_name else self.email.split("@")[0]

    @property
    def initials(self) -> str:
        parts = self.display_name.split()
        return "".join(p[0] for p in parts[:2]).upper() or "?"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=150, blank=True)
    # Login identifier and bill-payment recipient match. Stored in E.164.
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)

    def __str__(self):
        return self.full_name or self.user.email


class BankAccount(models.Model):
    """A user's payout bank account. The account number is encrypted at rest."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="bank_account")
    bank_code = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=150)
    account_number = EncryptedTextField()
    account_last4 = models.CharField(max_length=4, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.account_last4 = (self.account_number or "")[-4:]
        super().save(*args, **kwargs)

    @property
    def masked_number(self) -> str:
        return f"******{self.account_last4}"

    def __str__(self):
        return f"{self.bank_name} {self.masked_number}"
