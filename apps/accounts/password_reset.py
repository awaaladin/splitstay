"""Forgotten-password emails, for the website and the REST API.

Never reveals whether an email has an account (the answer is always "if it exists, we sent a link").
The link carries Django's signed, single-use, expiring token (PASSWORD_RESET_TIMEOUT)."""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.notifications import mailer

log = logging.getLogger(__name__)
User = get_user_model()


def request_reset(email: str) -> None:
    email = (email or "").strip()
    if not email:
        return
    for user in User.objects.filter(email__iexact=email, is_active=True):
        if not user.has_usable_password():
            continue
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.SITE_URL.rstrip('/')}/password-reset/{uid}/{token}/"
        mailer.send_email(user.email, "Reset your SplitPay password", "password_reset", {"reset_url": link})


def user_for(uid: str, token: str):
    """The user the link belongs to, or None when the link is wrong, used, or expired."""
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(uid).decode(), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError, UnicodeDecodeError):
        return None
    return user if default_token_generator.check_token(user, token) else None


def confirm_reset(uid: str, token: str, password: str):
    """Sets the new password. Raises ValidationError with readable messages when it cannot."""
    user = user_for(uid, token)
    if user is None:
        raise ValidationError("This reset link is invalid or has expired. Ask for a new one.")
    validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=["password"])
    return user
