from rest_framework import serializers

from apps.payouts.serializers import FeeSerializer

from .models import BillPayment


class BillPaymentSerializer(serializers.ModelSerializer):
    fees = FeeSerializer(many=True, read_only=True)
    biller = serializers.CharField(source="biller_name", read_only=True)

    class Meta:
        model = BillPayment
        fields = (
            "id", "group", "status", "reference", "biller", "service_id", "customer_id", "variation",
            "gross_amount", "fee_amount", "net_amount", "fees", "token", "units", "customer_name",
            "provider_reference", "is_partial", "failure_reason", "created_at", "completed_at",
        )
        read_only_fields = fields


class ValidateMeterSerializer(serializers.Serializer):
    service_id = serializers.CharField()
    customer_id = serializers.CharField()
    variation = serializers.CharField(required=False, allow_blank=True, default="prepaid")


class BillerSerializer(serializers.Serializer):
    service_id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    variations = serializers.ListField(child=serializers.CharField())
    customer_label = serializers.CharField()
