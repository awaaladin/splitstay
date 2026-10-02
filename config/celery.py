import os

from celery import Celery

# On Vercel (VERCEL=1) default to the serverless settings; locally default to dev.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.vercel" if os.environ.get("VERCEL") else "config.settings.dev",
)

app = Celery("splitstay")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
