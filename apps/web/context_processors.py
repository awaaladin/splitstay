from django.conf import settings

from apps.notifications.models import Notification

APP_USER_AGENT = "SplitPayAndroid"  # added by the Android app's WebView


def seo(request):
    """The public origin, so canonical and social URLs are the same on every host alias."""
    return {
        "site_url": settings.SITE_URL.rstrip("/"),
        "in_app": APP_USER_AGENT in request.headers.get("User-Agent", ""),
    }


def shell(request):
    """Data every page's header needs: the unread badge and the bell dropdown."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    unread = Notification.objects.filter(user=user, read_at__isnull=True).count()
    return {
        "unread_count": unread,
        "bell_notifications": list(Notification.objects.filter(user=user)[:6]),
    }
