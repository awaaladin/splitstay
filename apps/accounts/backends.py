from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .phone import normalize_phone


class EmailOrPhoneBackend(ModelBackend):
    """Authenticate with either an email address or a phone number."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        username = username or kwargs.get(User.USERNAME_FIELD)
        if not username or not password:
            return None
        username = username.strip()
        if "@" in username:
            user = User.objects.filter(email__iexact=username).first()
        else:
            user = User.objects.filter(profile__phone_number=normalize_phone(username)).first()
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
