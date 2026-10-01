from django.contrib import admin

from .models import Notification, NotificationDelivery


class DeliveryInline(admin.TabularInline):
    model = NotificationDelivery
    extra = 0


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "title", "created_at", "read_at")
    list_filter = ("kind",)
    inlines = [DeliveryInline]
