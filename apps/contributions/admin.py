from django.contrib import admin

from .models import Contribution


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ("reference", "group", "member", "amount", "status", "needs_review", "paid_at")
    list_filter = ("status", "needs_review")
    search_fields = ("reference", "gateway_reference", "member__email")
    readonly_fields = ("reference", "created_at", "paid_at")
