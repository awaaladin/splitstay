from apps.notifications.models import Notification


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
