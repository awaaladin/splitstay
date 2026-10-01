from django.contrib import admin

from apps.payouts.admin import FeeInline

from .models import BillPayment


@admin.register(BillPayment)
class BillPaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "group", "service_id", "gross_amount", "fee_amount", "net_amount", "status")
    list_filter = ("status", "service_id")
    inlines = [FeeInline]
