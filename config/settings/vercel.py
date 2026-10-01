"""Settings for Vercel's serverless Python runtime.

Differences from prod.py:
  * No Celery worker/Beat: tasks run inline (eager) and scheduled jobs are driven by Vercel Cron
    (see config/cron.py and vercel.json).
  * Static files are served by WhiteNoise straight from the source tree (no collectstatic step).
  * Cache uses REDIS_URL if provided (e.g. Upstash), otherwise per-instance memory.
  * Database connections are not pooled per process (each invocation may be a fresh instance).
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import DATABASES, FIELD_ENCRYPTION_KEY, PAYMENT_GATEWAY, PAYSTACK_SECRET_KEY, SECRET_KEY, env, env_bool, env_list

DEBUG = False

for _name, _value in {
    "DJANGO_SECRET_KEY": SECRET_KEY,
    "FIELD_ENCRYPTION_KEY": FIELD_ENCRYPTION_KEY,
    "DATABASE_URL": env("DATABASE_URL"),
    "CRON_SECRET": env("CRON_SECRET"),
}.items():
    if not _value:
        raise ImproperlyConfigured(f"{_name} must be set for the Vercel deployment")

# The offline sandbox gateway moves no real money. Only allow it for an explicit demo deployment.
DEMO_MODE = env_bool("ALLOW_DEMO_MODE", False)
if PAYMENT_GATEWAY == "mock" and not DEMO_MODE:
    raise ImproperlyConfigured("PAYMENT_GATEWAY=mock requires ALLOW_DEMO_MODE=1 (demo deployments only)")
if PAYMENT_GATEWAY == "paystack" and not PAYSTACK_SECRET_KEY:
    raise ImproperlyConfigured("PAYSTACK_SECRET_KEY must be set")

CRON_SECRET = env("CRON_SECRET")

# --- Hosts / origins ---------------------------------------------------------------------
_vercel_hosts = [h for h in (env("VERCEL_URL"), env("VERCEL_PROJECT_PRODUCTION_URL")) if h]
ALLOWED_HOSTS = [".vercel.app", *_vercel_hosts, *env_list("DJANGO_ALLOWED_HOSTS", "")]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in _vercel_hosts] + env_list("CSRF_TRUSTED_ORIGINS", "")
if not env("SITE_URL") and env("VERCEL_PROJECT_PRODUCTION_URL"):
    SITE_URL = f"https://{env('VERCEL_PROJECT_PRODUCTION_URL')}"

# --- Database: serverless => no persistent connections -----------------------------------
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
if "postgres" in DATABASES["default"]["ENGINE"]:
    DATABASES["default"].setdefault("OPTIONS", {}).setdefault("sslmode", env("DB_SSLMODE", "require"))

# --- Celery: run inline; Vercel Cron drives the schedule -----------------------------------
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False

# --- Cache -------------------------------------------------------------------------------
if env("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": env("REDIS_URL"),
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    # Throttling counters are then per instance (weaker). Set REDIS_URL (Upstash) for shared limits.
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Security / static ---------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Vercel terminates TLS and redirects http -> https itself
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True

WHITENOISE_USE_FINDERS = True  # serve from static/ and app static dirs; nothing to collect at build time
WHITENOISE_AUTOREFRESH = False
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Vercel's filesystem is read-only apart from /tmp, so uploaded avatars are not persisted.
MEDIA_ROOT = "/tmp/media"

LOGGING["root"]["level"] = env("LOG_LEVEL", "INFO")  # noqa: F405
