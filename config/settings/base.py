"""Base settings shared by every environment. All secrets come from the environment."""
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import dj_database_url
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_dotenv(path):
    """Minimal .env loader for local runs. Real environment variables always win (so Vercel/Docker are unaffected)."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0]  # allow trailing "  # comment"
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "drf_spectacular",
    "apps.accounts",
    "apps.groups",
    "apps.contributions",
    "apps.payments",
    "apps.billpay",
    "apps.payouts",
    "apps.recurrence",
    "apps.notifications",
    "apps.ledger",
    "apps.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.web.context_processors.shell",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://splitstay:splitstay@localhost:5432/splitstay"),
        conn_max_age=60,
    )
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailOrPhoneBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "web:login"
LOGIN_REDIRECT_URL = "web:dashboard"
LOGOUT_REDIRECT_URL = "web:landing"

# --- Cache / Celery -------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_BEAT_SCHEDULE = {
    "send-due-reminders": {
        "task": "apps.notifications.tasks.send_due_reminders",
        "schedule": crontab(hour=8, minute=0),
    },
    "enforce-deadlines": {
        "task": "apps.groups.tasks.enforce_deadlines",
        "schedule": crontab(hour=0, minute=15),
    },
    "spawn-recurring-cycles": {
        "task": "apps.recurrence.tasks.spawn_due_cycles",
        "schedule": crontab(hour=1, minute=0),
    },
    "reconcile-pending-payouts": {
        "task": "apps.payouts.tasks.reconcile_pending",
        "schedule": crontab(minute="*/10"),
    },
}

# --- DRF / JWT / OpenAPI ---------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.accounts.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.accounts.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("THROTTLE_AUTH", "10/min"),
        "group_create": env("THROTTLE_GROUP_CREATE", "20/hour"),
    },
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
SPECTACULAR_SETTINGS = {
    "TITLE": "SplitStay API",
    "DESCRIPTION": "Group contribution and bill-payment platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- CORS ------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# --- Money ----------------------------------------------------------------
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")  # urlsafe-base64 Fernet key

# Which collection/disbursement gateway to use: "paystack" or "mock".
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", "mock")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
PAYSTACK_BASE_URL = env("PAYSTACK_BASE_URL", "https://api.paystack.co")
SITE_URL = env("SITE_URL", "http://localhost:8000")

# Bill providers: "vtpass" or "mock".
BILL_PROVIDER = env("BILL_PROVIDER", "mock")
VTPASS_BASE_URL = env("VTPASS_BASE_URL", "https://sandbox.vtpass.com/api")
VTPASS_API_KEY = env("VTPASS_API_KEY", "")
VTPASS_SECRET_KEY = env("VTPASS_SECRET_KEY", "")
VTPASS_PUBLIC_KEY = env("VTPASS_PUBLIC_KEY", "")

# Service fee applied at payout time: "flat" (naira) or "percent".
SERVICE_FEE_TYPE = env("SERVICE_FEE_TYPE", "flat")
SERVICE_FEE_FLAT = Decimal(env("SERVICE_FEE_FLAT", "150"))
SERVICE_FEE_PERCENT = Decimal(env("SERVICE_FEE_PERCENT", "1.5"))
SERVICE_FEE_MIN = Decimal(env("SERVICE_FEE_MIN", "0"))
SERVICE_FEE_MAX = Decimal(env("SERVICE_FEE_MAX", "0"))  # 0 = no cap

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
