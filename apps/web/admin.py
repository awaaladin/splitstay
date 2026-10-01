from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "topic", "name", "email", "is_resolved")
    list_filter = ("topic", "is_resolved")
    search_fields = ("name", "email", "message", "reference")
    readonly_fields = ("name", "email", "topic", "message", "reference", "user", "created_at")
