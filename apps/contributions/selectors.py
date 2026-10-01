"""Read-side helpers. Totals are always computed from confirmed contributions, never cached."""
from decimal import Decimal

from django.db.models import Sum

from .models import Contribution


def total_funded(group) -> Decimal:
    return Contribution.objects.filter(group=group).total()


def member_paid(group, user) -> Decimal:
    return Contribution.objects.filter(group=group, member=user).total()


def progress(group) -> dict:
    funded = total_funded(group)
    target = group.target_amount
    percent = min(funded / target * 100, Decimal("100")) if target else Decimal("0")
    return {
        "target": target,
        "funded": funded,
        "remaining": max(target - funded, Decimal("0.00")),
        "percent": percent.quantize(Decimal("0.1")),
        "is_funded": funded >= target,
    }


def paid_totals_by_member(group) -> dict[int, Decimal]:
    rows = (
        Contribution.objects.filter(group=group, status="paid").values("member_id").annotate(t=Sum("amount"))
    )
    return {row["member_id"]: row["t"] for row in rows}
