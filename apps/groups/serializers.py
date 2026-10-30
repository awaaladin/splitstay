from datetime import date

from django.conf import settings
from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer
from apps.billpay import catalog
from apps.contributions.selectors import progress
from apps.payouts.fees import fee_for_payment

from .models import ContributionGroup, GroupMembership, PayoutType
from .services import find_user


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    amount_paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = GroupMembership
        fields = ("user", "contribution_share", "is_custom_share", "status", "amount_paid", "outstanding", "joined_at")
        read_only_fields = fields


class GroupSerializer(serializers.ModelSerializer):
    admin = UserSummarySerializer(read_only=True)
    progress = serializers.SerializerMethodField()
    my_membership = serializers.SerializerMethodField()
    recipient_account = serializers.CharField(source="masked_recipient_account", read_only=True)
    biller_name = serializers.SerializerMethodField()
    pay_quote = serializers.SerializerMethodField()
    needs_review = serializers.SerializerMethodField()

    class Meta:
        model = ContributionGroup
        fields = (
            "id", "name", "description", "purpose", "target_amount", "due_date", "is_recurring",
            "recurrence_interval", "status", "admin", "payout_type", "allow_partial_payout",
            "bill_service_id", "biller_name", "bill_customer_id", "bill_variation",
            "recipient_bank_code", "recipient_bank_name", "recipient_account_name", "recipient_account",
            "cycle_number", "previous_cycle", "funded_at", "created_at", "progress", "my_membership",
            "pay_quote", "needs_review",
        )
        read_only_fields = fields

    @extend_schema_field(inline_serializer("GroupProgress", {
        "target": serializers.DecimalField(14, 2), "funded": serializers.DecimalField(14, 2),
        "remaining": serializers.DecimalField(14, 2), "percent": serializers.DecimalField(5, 1),
        "is_funded": serializers.BooleanField(),
    }))
    def get_progress(self, obj):
        return progress(obj)

    @extend_schema_field(MembershipSerializer(allow_null=True))
    def get_my_membership(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        membership = obj.memberships.filter(user=request.user).exclude(status="left").first()
        return MembershipSerializer(membership).data if membership else None

    @extend_schema_field(inline_serializer("PayQuote", {
        "share": serializers.DecimalField(14, 2), "fee": serializers.DecimalField(14, 2),
        "total": serializers.DecimalField(14, 2),
    }, allow_null=True))
    def get_pay_quote(self, obj):
        """What paying the requester's outstanding share would charge right now, shown before they commit."""
        request = self.context.get("request")
        membership = obj.memberships.filter(user=request.user, status="joined").first() if request else None
        if not membership or not obj.is_open_for_contributions or membership.outstanding <= 0:
            return None
        fee = fee_for_payment(membership.outstanding, obj.target_amount).amount
        return {"share": membership.outstanding, "fee": fee, "total": membership.outstanding + fee}

    def get_needs_review(self, obj) -> bool:
        request = self.context.get("request")
        if not request or obj.admin_id != request.user.pk:
            return False
        return obj.contributions.filter(needs_review=True).exists()

    def get_biller_name(self, obj) -> str:
        biller = catalog.get_biller(obj.bill_service_id)
        return biller.name if biller else ""


class MemberInputSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Email address or phone number of an existing SplitPay user")
    contribution_share = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=1)

    def validate_identifier(self, value):
        user = find_user(value)
        if user is None:
            raise serializers.ValidationError(f"No SplitPay account found for '{value}'.")
        self.context["resolved_user"] = user
        return value


class GroupWriteSerializer(serializers.ModelSerializer):
    recipient_account_number = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=10)
    members = MemberInputSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = ContributionGroup
        fields = (
            "name", "description", "purpose", "target_amount", "due_date", "is_recurring", "recurrence_interval",
            "payout_type", "allow_partial_payout", "bill_service_id", "bill_customer_id", "bill_variation",
            "recipient_bank_code", "recipient_bank_name", "recipient_account_name", "recipient_account_number",
            "members",
        )

    def validate_due_date(self, value):
        if self.instance is None and value < date.today():
            raise serializers.ValidationError("The due date cannot be in the past.")
        return value

    def validate_target_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("The target must be more than zero.")
        return value

    def validate_recipient_account_number(self, value):
        if value and not (value.isdigit() and len(value) == 10):
            raise serializers.ValidationError("Account numbers are 10 digits.")
        return value

    def validate(self, attrs):
        payout_type = attrs.get("payout_type", getattr(self.instance, "payout_type", None))
        if payout_type == PayoutType.BILL_PAYMENT and self.instance is None and not settings.BILL_PAYMENTS_ENABLED:
            raise serializers.ValidationError({"payout_type": "Electricity bill payment isn't switched on yet."})
        if payout_type == PayoutType.BILL_PAYMENT:
            service = attrs.get("bill_service_id", getattr(self.instance, "bill_service_id", ""))
            biller = catalog.get_biller(service)
            if biller is None:
                raise serializers.ValidationError({"bill_service_id": "Choose a supported biller."})
            variation = attrs.get("bill_variation", getattr(self.instance, "bill_variation", ""))
            if biller.variations and variation not in biller.variations:
                raise serializers.ValidationError({"bill_variation": f"Choose one of: {', '.join(biller.variations)}."})
        return attrs
