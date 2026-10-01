from django.conf import settings
from django.db import models


class Kind(models.TextChoices):
    INVITED = "invited", "Group invitation"
    CONTRIBUTION = "contribution", "Contribution received"
    FUNDED = "funded", "Target reached"
    PAYOUT_DONE = "payout_done", "Payout completed"
    PAYOUT_FAILED = "payout_failed", "Payout failed"
    REMINDER = "reminder", "Payment reminder"
    OVERDUE = "overdue", "Group overdue"
    CYCLE = "cycle", "New cycle opened"


class Notification(models.Model):
    """Channel-independent message content. Delivery per channel lives in NotificationDelivery,
    so adding push/SMS later means writing a channel handler, not changing this schema."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=140)
    body = models.TextField(blank=True)
    group = models.ForeignKey(
        "groups.ContributionGroup", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    data = models.JSONField(default=dict, blank=True)
    # Makes reminders/events safe to emit twice: the same key never creates a second row.
    dedupe_key = models.CharField(max_length=150, null=True, blank=True, unique=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self):
        return f"{self.kind} -> {self.user}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class Channel(models.TextChoices):
    IN_APP = "in_app", "In-app"
    PUSH = "push", "Push"
    SMS = "sms", "SMS"
    EMAIL = "email", "Email"


class NotificationDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=250, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["notification", "channel"], name="one_delivery_per_channel")]
