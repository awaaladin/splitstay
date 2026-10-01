from django.conf import settings
from django.db import models


class ContactMessage(models.Model):
    """Messages sent through the public contact form. Read them in the Django admin."""

    class Topic(models.TextChoices):
        HELP = "help", "I need help using SplitStay"
        PAYMENT = "payment", "A payment or payout question"
        BUG = "bug", "Something isn't working"
        IDEA = "idea", "An idea or feedback"
        OTHER = "other", "Something else"

    name = models.CharField(max_length=120)
    email = models.EmailField()
    topic = models.CharField(max_length=10, choices=Topic.choices, default=Topic.HELP)
    message = models.TextField(max_length=4000)
    reference = models.CharField(max_length=60, blank=True, help_text="Group name or payment reference, if any")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_topic_display()} from {self.email}"
