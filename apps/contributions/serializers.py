from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer

from .models import Contribution


class ContributionSerializer(serializers.ModelSerializer):
    member = UserSummarySerializer(read_only=True)
    charge_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True,
                                             help_text="What the member is charged: amount plus service_fee")

    class Meta:
        model = Contribution
        fields = ("id", "group", "member", "amount", "service_fee", "charge_amount", "status", "reference",
                  "created_at", "paid_at")
        read_only_fields = fields


class ContributeSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=1)
