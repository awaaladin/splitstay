from django.db import models


class WebhookEvent(models.Model):
    """One row per distinct gateway event. The unique key is what makes retries harmless."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=150)
    event_type = models.CharField(max_length=50)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    payload = models.JSONField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    error = models.TextField(blank=True)
    delivery_count = models.PositiveIntegerField(default=1)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="unique_webhook_event")]

    def __str__(self):
        return f"{self.provider}:{self.event_id} ({self.status})"
