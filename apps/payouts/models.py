import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounts.fields import EncryptedTextField


class PayoutStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


def new_payout_reference() -> str:
    # Paystack transfer references must be lowercase alphanumerics, dashes or underscores.
    return f"cp-po-{uuid.uuid4().hex[:24]}"


class Payout(models.Model):
    """Bank transfer to the group's designated recipient. Tracked apart from contribution collection."""

    group = models.OneToOneField("groups.ContributionGroup", on_delete=models.PROTECT, related_name="payout")
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2)
    net_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=PayoutStatus.choices, default=PayoutStatus.PENDING, db_index=True)
    reference = models.CharField(max_length=60, unique=True, default=new_payout_reference)
    attempts = models.PositiveIntegerField(default=0)
    gateway = models.CharField(max_length=20, blank=True)
    gateway_reference = models.CharField(max_length=100, blank=True)
    failure_reason = models.CharField(max_length=250, blank=True)
    is_partial = models.BooleanField(default=False)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    # Snapshot of the destination at the moment of payout, so later edits can't rewrite history.
    recipient_bank_code = models.CharField(max_length=10)
    recipient_bank_name = models.CharField(max_length=100)
    recipient_account_name = models.CharField(max_length=150)
    recipient_account_number = EncryptedTextField()
    recipient_account_last4 = models.CharField(max_length=4)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(net_amount__gt=0), name="payout_net_positive"),
        ]

    def __str__(self):
        return f"Payout {self.reference} ({self.status})"

    @property
    def masked_account(self) -> str:
        return f"******{self.recipient_account_last4}"


class Fee(models.Model):
    """An explicit, auditable service-fee line attached to exactly one Payout or BillPayment."""

    class FeeType(models.TextChoices):
        FLAT = "flat", "Flat"
        PERCENT = "percent", "Percentage"

    payout = models.ForeignKey(Payout, null=True, blank=True, on_delete=models.CASCADE, related_name="fees")
    bill_payment = models.ForeignKey(
        "billpay.BillPayment", null=True, blank=True, on_delete=models.CASCADE, related_name="fees"
    )
    fee_type = models.CharField(max_length=8, choices=FeeType.choices)
    rate = models.DecimalField(max_digits=10, decimal_places=4, help_text="Naira if flat, percent if percentage")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=120, default="SplitStay service fee")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(payout__isnull=False, bill_payment__isnull=True)
                           | Q(payout__isnull=True, bill_payment__isnull=False)),
                name="fee_belongs_to_exactly_one",
            )
        ]

    def __str__(self):
        return f"{self.description}: {self.amount}"
