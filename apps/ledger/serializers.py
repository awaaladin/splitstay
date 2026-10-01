from rest_framework import serializers


class LedgerEntrySerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    kind = serializers.CharField()
    title = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    status = serializers.CharField()
    actor = serializers.CharField(allow_blank=True)
    reference = serializers.CharField(allow_blank=True)
    detail = serializers.DictField()


class MemberStandingSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    share = serializers.DecimalField(max_digits=14, decimal_places=2)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    state = serializers.CharField()
