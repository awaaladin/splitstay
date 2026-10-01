from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from apps.accounts.fields import EncryptedTextField


class Purpose(models.TextChoices):
    RENT = "rent", "Rent"
    ELECTRICITY = "electricity", "Electricity (NEPA)"
    SUBSCRIPTION = "subscription", "Subscription"
    FAMILY = "family_upkeep", "Family upkeep"
    CUSTOM = "custom", "Custom"


class Interval(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    ANNUAL = "annual", "Annual"

    @property
    def months(self) -> int:
        return {"monthly": 1, "quarterly": 3, "annual": 12}[self.value]


class GroupStatus(models.TextChoices):
    OPEN = "open", "Open"
    FUNDED = "funded", "Funded"
    PAID_OUT = "paid_out", "Paid out"
    CANCELLED = "cancelled", "Cancelled"
    OVERDUE = "overdue", "Overdue"


class PayoutType(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    BILL_PAYMENT = "bill_payment", "Bill payment"


class ContributionGroup(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.CUSTOM)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    due_date = models.DateField()
    is_recurring = models.BooleanField(default=False)
    recurrence_interval = models.CharField(max_length=10, choices=Interval.choices, null=True, blank=True)
    status = models.CharField(max_length=10, choices=GroupStatus.choices, default=GroupStatus.OPEN, db_index=True)
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="administered_groups")
    payout_type = models.CharField(max_length=15, choices=PayoutType.choices)
    # Admin may trigger payout before the target is reached.
    allow_partial_payout = models.BooleanField(default=False)

    # Bill-payment destination (payout_type = bill_payment)
    bill_service_id = models.CharField(max_length=60, blank=True, help_text="Biller code, e.g. ikeja-electric")
    bill_customer_id = models.CharField(max_length=40, blank=True, help_text="Meter number / smartcard / account")
    bill_variation = models.CharField(max_length=20, blank=True, help_text="prepaid / postpaid")

    # Bank-transfer destination (payout_type = bank_transfer)
    recipient_bank_code = models.CharField(max_length=10, blank=True)
    recipient_bank_name = models.CharField(max_length=100, blank=True)
    recipient_account_name = models.CharField(max_length=150, blank=True)
    recipient_account_number = EncryptedTextField(blank=True, default="")

    # Recurrence: each cycle is its own group, chained through previous_cycle.
    # The OneToOne guarantees a cycle can only ever spawn one successor.
    previous_cycle = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="next_cycle"
    )
    cycle_number = models.PositiveIntegerField(default=1)
    series_anchor_date = models.DateField(help_text="Due date of cycle 1; later cycles are offset from it")

    funded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(target_amount__gt=0), name="group_target_positive"),
            models.CheckConstraint(
                condition=models.Q(is_recurring=False) | models.Q(recurrence_interval__isnull=False),
                name="group_recurring_needs_interval",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def total_funded(self) -> Decimal:
        """Always derived from confirmed contributions; never stored."""
        total = self.contributions.filter(status="paid").aggregate(t=Sum("amount"))["t"]
        return total or Decimal("0.00")

    @property
    def remaining(self) -> Decimal:
        return max(self.target_amount - self.total_funded, Decimal("0.00"))

    @property
    def percent_funded(self) -> Decimal:
        if not self.target_amount:
            return Decimal("0")
        return min(self.total_funded / self.target_amount * 100, Decimal("100")).quantize(Decimal("0.1"))

    @property
    def is_open_for_contributions(self) -> bool:
        return self.status in (GroupStatus.OPEN, GroupStatus.OVERDUE)

    @property
    def masked_recipient_account(self) -> str:
        number = self.recipient_account_number or ""
        return f"******{number[-4:]}" if number else ""

    @property
    def biller_name(self) -> str:
        from apps.billpay.catalog import get_biller

        biller = get_biller(self.bill_service_id)
        return biller.name if biller else self.bill_service_id

    @property
    def days_until_due(self) -> int:
        return (self.due_date - date.today()).days

    def clean(self):
        if self.is_recurring and not self.recurrence_interval:
            raise ValidationError({"recurrence_interval": "Recurring groups need an interval."})
        if not self.is_recurring:
            self.recurrence_interval = None
        if self.payout_type == PayoutType.BILL_PAYMENT and not (self.bill_service_id and self.bill_customer_id):
            raise ValidationError("Bill-payment groups need a biller and a meter/customer number.")
        if self.payout_type == PayoutType.BANK_TRANSFER and not (
            self.recipient_bank_code and self.recipient_account_number and self.recipient_account_name
        ):
            raise ValidationError("Bank-transfer groups need recipient bank details.")


class MembershipStatus(models.TextChoices):
    INVITED = "invited", "Invited"
    JOINED = "joined", "Joined"
    LEFT = "left", "Left"


class GroupMembership(models.Model):
    group = models.ForeignKey(ContributionGroup, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_memberships")
    contribution_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    # True when the admin set this amount by hand; equal-split rebalancing skips it.
    is_custom_share = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=MembershipStatus.choices, default=MembershipStatus.INVITED)
    invited_at = models.DateTimeField(auto_now_add=True)
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["group", "user"], name="unique_group_member")]

    def __str__(self):
        return f"{self.user} in {self.group}"

    @property
    def amount_paid(self) -> Decimal:
        total = self.group.contributions.filter(member_id=self.user_id, status="paid").aggregate(t=Sum("amount"))["t"]
        return total or Decimal("0.00")

    @property
    def outstanding(self) -> Decimal:
        return max(self.contribution_share - self.amount_paid, Decimal("0.00"))
