import os

from django.core.wsgi import get_wsgi_application

# Vercel sets VERCEL=1 at runtime and auto-detects this module as the Django entrypoint, so use the
# serverless settings there. Elsewhere (Docker/gunicorn) default to the strict production settings.
# An explicit DJANGO_SETTINGS_MODULE always wins.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.vercel" if os.environ.get("VERCEL") else "config.settings.prod",
)
application = get_wsgi_application()
# Some Vercel runtimes look for `app`.
app = application
