from .base import *  # noqa: F401,F403
from .base import env, env_bool

DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-do-not-use-in-production"  # noqa: F405
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_EAGER", False)

# Running without Docker/Redis? Set DJANGO_CACHE=locmem and CELERY_EAGER=1 (with a sqlite DATABASE_URL).
if env("DJANGO_CACHE") == "locmem":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# WhiteNoise serves /static/ in dev too; no need for collectstatic.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
