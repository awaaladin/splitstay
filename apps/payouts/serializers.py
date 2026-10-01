from rest_framework import serializers

from .models import Fee, Payout


class FeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fee
        fields = ("description", "fee_type", "rate", "amount")


class PayoutSerializer(serializers.ModelSerializer):
    fees = FeeSerializer(many=True, read_only=True)
    recipient_account = serializers.CharField(source="masked_account", read_only=True)

    class Meta:
        model = Payout
        fields = (
            "id", "group", "status", "reference", "gross_amount", "fee_amount", "net_amount", "fees",
            "recipient_bank_name", "recipient_account_name", "recipient_account", "is_partial",
            "failure_reason", "created_at", "completed_at",
        )
        read_only_fields = fields
