from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum

from apps.payments.naming import make_reference


class ContributionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"


def new_reference() -> str:
    return make_reference("CONTRIB")


class ContributionQuerySet(models.QuerySet):
    def confirmed(self):
        return self.filter(status=ContributionStatus.PAID)

    def total(self):
        """Sum of confirmed contributions in this queryset. This is the ONLY definition of 'funded'."""
        from decimal import Decimal

        return self.confirmed().aggregate(t=Sum("amount"))["t"] or Decimal("0.00")


class Contribution(models.Model):
    group = models.ForeignKey("groups.ContributionGroup", on_delete=models.PROTECT, related_name="contributions")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contributions")
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # credited to the group's pot
    # SplitPay's fee, charged ON TOP of `amount` at checkout. It never enters the pot or the payout.
    service_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=10, choices=ContributionStatus.choices, default=ContributionStatus.PENDING, db_index=True
    )
    # Our own reference, sent to the gateway and echoed back in its webhook.
    reference = models.CharField(max_length=40, unique=True, default=new_reference, editable=False)
    gateway = models.CharField(max_length=20, blank=True)
    gateway_reference = models.CharField(max_length=100, blank=True)
    checkout_url = models.URLField(max_length=500, blank=True)
    # What the gateway charged us to collect this payment (from Paystack), for profit/loss accounts.
    gateway_fee = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    failure_reason = models.CharField(max_length=200, blank=True)
    # Money arrived in a state we can't auto-reconcile (group already closed, overpayment, ...).
    needs_review = models.BooleanField(default=False)
    review_note = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    objects = ContributionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="contribution_amount_positive")]
        indexes = [models.Index(fields=["group", "status"])]

    def __str__(self):
        return f"{self.reference} {self.amount} ({self.status})"

    @property
    def charge_amount(self) -> Decimal:
        """What the member is actually charged at checkout: their share plus SplitPay's fee."""
        return self.amount + self.service_fee
