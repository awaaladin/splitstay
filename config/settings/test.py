"""Test settings: in-memory SQLite, local-memory cache, eager Celery, fast hashing."""
from .base import *  # noqa: F401,F403

SECRET_KEY = "test-secret-key"
DEBUG = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
PAYMENT_GATEWAY = "mock"
BILL_PROVIDER = "mock"
PAYSTACK_SECRET_KEY = "sk_test_unit"
SERVICE_FEE_TYPE = "flat"
SERVICE_FEE_FLAT = 150
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"auth": "1000/min", "group_create": "1000/min"}}  # noqa: F405
