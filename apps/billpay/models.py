import uuid
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.payouts.models import PayoutStatus


def new_bill_reference() -> str:
    # VTpass request ids must start with the current Lagos time as YYYYMMDDHHmm.
    stamp = timezone.now().astimezone(ZoneInfo("Africa/Lagos")).strftime("%Y%m%d%H%M")
    return f"{stamp}{uuid.uuid4().hex[:14]}"


class BillPayment(models.Model):
    """A bill paid from a funded group's pool (payout_type = bill_payment)."""

    group = models.OneToOneField("groups.ContributionGroup", on_delete=models.PROTECT, related_name="bill_payment")
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2)
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Amount actually sent to the biller")
    status = models.CharField(max_length=12, choices=PayoutStatus.choices, default=PayoutStatus.PENDING, db_index=True)
    reference = models.CharField(max_length=60, unique=True, default=new_bill_reference)
    attempts = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=20, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True)

    service_id = models.CharField(max_length=60)
    customer_id = models.CharField(max_length=40)
    variation = models.CharField(max_length=20, blank=True)
    customer_name = models.CharField(max_length=150, blank=True)

    token = models.CharField(max_length=100, blank=True, help_text="Electricity token, when applicable")
    units = models.CharField(max_length=40, blank=True)
    failure_reason = models.CharField(max_length=250, blank=True)
    is_partial = models.BooleanField(default=False)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(net_amount__gt=0), name="billpay_net_positive")]

    def __str__(self):
        return f"Bill {self.reference} ({self.status})"

    @property
    def biller_name(self) -> str:
        from .catalog import get_biller

        biller = get_biller(self.service_id)
        return biller.name if biller else self.service_id
