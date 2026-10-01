from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer

from .models import Contribution


class ContributionSerializer(serializers.ModelSerializer):
    member = UserSummarySerializer(read_only=True)

    class Meta:
        model = Contribution
        fields = ("id", "group", "member", "amount", "status", "reference", "created_at", "paid_at")
        read_only_fields = fields


class ContributeSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=1)
