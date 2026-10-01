from datetime import date

from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer
from apps.billpay import catalog
from apps.contributions.selectors import progress

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

    class Meta:
        model = ContributionGroup
        fields = (
            "id", "name", "description", "purpose", "target_amount", "due_date", "is_recurring",
            "recurrence_interval", "status", "admin", "payout_type", "allow_partial_payout",
            "bill_service_id", "biller_name", "bill_customer_id", "bill_variation",
            "recipient_bank_name", "recipient_account_name", "recipient_account",
            "cycle_number", "previous_cycle", "funded_at", "created_at", "progress", "my_membership",
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

    def get_biller_name(self, obj) -> str:
        biller = catalog.get_biller(obj.bill_service_id)
        return biller.name if biller else ""


class MemberInputSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Email address or phone number of an existing SplitStay user")
    contribution_share = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=1)

    def validate_identifier(self, value):
        user = find_user(value)
        if user is None:
            raise serializers.ValidationError(f"No SplitStay account found for '{value}'.")
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
        if payout_type == PayoutType.BILL_PAYMENT:
            service = attrs.get("bill_service_id", getattr(self.instance, "bill_service_id", ""))
            biller = catalog.get_biller(service)
            if biller is None:
                raise serializers.ValidationError({"bill_service_id": "Choose a supported biller."})
            variation = attrs.get("bill_variation", getattr(self.instance, "bill_variation", ""))
            if biller.variations and variation not in biller.variations:
                raise serializers.ValidationError({"bill_variation": f"Choose one of: {', '.join(biller.variations)}."})
        return attrs
