from django.contrib import admin

from .models import Fee, Payout


class FeeInline(admin.TabularInline):
    model = Fee
    extra = 0
    readonly_fields = ("fee_type", "rate", "amount", "description")


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("reference", "group", "gross_amount", "fee_amount", "net_amount", "status")
    list_filter = ("status",)
    exclude = ("recipient_account_number",)
    inlines = [FeeInline]
