"""The transparent history of a group, built at read time from the source-of-truth records
(contributions, payout, bill payment, fees). Nothing here is stored, so it cannot drift."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.contributions.models import Contribution, ContributionStatus
from apps.contributions.selectors import paid_totals_by_member, progress
from apps.groups.models import ContributionGroup, PayoutType
from apps.groups.selectors import active_memberships


@dataclass
class Entry:
    at: datetime
    kind: str  # contribution | fee | payout | bill_payment | cycle
    title: str
    amount: Decimal | None
    status: str
    actor: str = ""
    reference: str = ""
    detail: dict = field(default_factory=dict)


def group_entries(group: ContributionGroup, *, user=None) -> list[Entry]:
    """Every money event for the group, newest first. Pending checkouts are omitted (not yet money)."""
    entries: list[Entry] = []
    contributions = group.contributions.exclude(status=ContributionStatus.PENDING).select_related(
        "member", "member__profile"
    )
    if user is not None:
        contributions = contributions.filter(member=user)
    for c in contributions:
        entries.append(Entry(
            at=c.paid_at or c.created_at, kind="contribution",
            title="Contribution" if c.status == ContributionStatus.PAID else "Contribution failed",
            amount=c.amount, status=c.status, actor=c.member.display_name, reference=c.reference,
            detail={"member_id": c.member_id, "needs_review": c.needs_review},
        ))
    if user is not None:
        return sorted(entries, key=lambda e: e.at, reverse=True)

    record = getattr(group, "bill_payment" if group.payout_type == PayoutType.BILL_PAYMENT else "payout", None)
    if record is not None:
        is_bill = group.payout_type == PayoutType.BILL_PAYMENT
        for fee in record.fees.all():
            entries.append(Entry(
                at=record.created_at, kind="fee", title=fee.description, amount=fee.amount, status="applied",
                reference=record.reference,
                detail={"fee_type": fee.fee_type, "rate": str(fee.rate)},
            ))
        entries.append(Entry(
            at=record.completed_at or record.created_at,
            kind="bill_payment" if is_bill else "payout",
            title=(f"Bill paid: {record.biller_name}" if is_bill else f"Transfer to {record.recipient_account_name}"),
            amount=record.net_amount, status=record.status, reference=record.reference,
            detail={"token": record.token, "units": record.units} if is_bill else {"account": record.masked_account},
        ))
    return sorted(entries, key=lambda e: e.at, reverse=True)


def member_rows(group: ContributionGroup) -> list[dict]:
    """Who has paid and who hasn't: the core of the 'ajo' trust model."""
    paid = paid_totals_by_member(group)
    rows = []
    for m in active_memberships(group):
        amount_paid = paid.get(m.user_id, Decimal("0.00"))
        outstanding = max(m.contribution_share - amount_paid, Decimal("0.00"))
        if m.status == "invited":
            state = "invited"
        elif outstanding == 0:
            state = "paid"
        elif amount_paid > 0:
            state = "partial"
        else:
            state = "unpaid"
        rows.append({
            "user": m.user, "membership": m, "share": m.contribution_share, "paid": amount_paid,
            "outstanding": outstanding, "state": state, "is_admin": m.user_id == group.admin_id,
        })
    return rows


def group_summary(group: ContributionGroup) -> dict:
    data = progress(group)
    record = getattr(group, "bill_payment" if group.payout_type == PayoutType.BILL_PAYMENT else "payout", None)
    data["payout_status"] = record.status if record else None
    data["fee"] = record.fee_amount if record else None
    data["net"] = record.net_amount if record else None
    return data
