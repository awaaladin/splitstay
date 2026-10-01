from django.contrib import admin

from .models import WebhookEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_id", "event_type", "status", "delivery_count", "received_at")
    list_filter = ("provider", "status", "event_type")
    search_fields = ("event_id", "reference")
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]
