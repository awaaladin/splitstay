from django.utils import timezone

from .models import Channel, Notification, NotificationDelivery


def _deliver_in_app(notification: Notification) -> None:
    """In-app delivery is the row itself; it is 'sent' the moment it exists."""


# Register push/SMS/email senders here; each receives the Notification and raises on failure.
CHANNEL_HANDLERS = {Channel.IN_APP: _deliver_in_app}


def notify(user, kind, title, body="", *, group=None, data=None, dedupe_key=None, channels=(Channel.IN_APP,)):
    """Create a notification (once per dedupe_key) and hand it to each channel."""
    if dedupe_key:
        existing = Notification.objects.filter(dedupe_key=dedupe_key).first()
        if existing:
            return existing
    notification = Notification.objects.create(
        user=user, kind=kind, title=title, body=body, group=group, data=data or {}, dedupe_key=dedupe_key
    )
    for channel in channels:
        delivery = NotificationDelivery.objects.create(notification=notification, channel=channel)
        handler = CHANNEL_HANDLERS.get(channel)
        if handler is None:
            continue  # stays pending until a handler for this channel is registered
        try:
            handler(notification)
            delivery.status = NotificationDelivery.Status.SENT
            delivery.sent_at = timezone.now()
        except Exception as exc:  # a failing SMS gateway must never break a payment flow
            delivery.status = NotificationDelivery.Status.FAILED
            delivery.last_error = str(exc)[:250]
        delivery.attempts += 1
        delivery.save()
    return notification


def mark_read(user, ids=None) -> int:
    qs = Notification.objects.filter(user=user, read_at__isnull=True)
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    return qs.update(read_at=timezone.now())


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()
