from django.contrib import admin

from .models import ContributionGroup, GroupMembership


class MembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0


@admin.register(ContributionGroup)
class ContributionGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "purpose", "target_amount", "due_date", "status", "admin", "cycle_number")
    list_filter = ("status", "purpose", "payout_type", "is_recurring")
    search_fields = ("name",)
    exclude = ("recipient_account_number",)
    inlines = [MembershipInline]
