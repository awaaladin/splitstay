import os

if os.environ.get("VERCEL"):
    # Running on Vercel's serverless runtime: use its settings even if DJANGO_SETTINGS_MODULE
    # was left pointing at prod (no persistent workers, inline tasks, WhiteNoise finders...).
    from .vercel import *  # noqa: F401,F403
else:
    from django.core.exceptions import ImproperlyConfigured

    from .base import *  # noqa: F401,F403
    from .base import FIELD_ENCRYPTION_KEY, PAYMENT_GATEWAY, PAYSTACK_SECRET_KEY, SECRET_KEY, env

    DEBUG = False

    for _name, _value in {
        "DJANGO_SECRET_KEY": SECRET_KEY,
        "FIELD_ENCRYPTION_KEY": FIELD_ENCRYPTION_KEY,
        "DATABASE_URL": env("DATABASE_URL"),
    }.items():
        if not _value:
            raise ImproperlyConfigured(f"{_name} must be set in production")
    if PAYMENT_GATEWAY == "mock":
        raise ImproperlyConfigured("PAYMENT_GATEWAY=mock is not allowed in production")
    if PAYMENT_GATEWAY == "paystack" and not PAYSTACK_SECRET_KEY:
        raise ImproperlyConfigured("PAYSTACK_SECRET_KEY must be set")

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", "true") == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
