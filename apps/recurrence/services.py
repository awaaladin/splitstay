from datetime import date

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from apps.groups.models import (
    ContributionGroup,
    GroupMembership,
    GroupStatus,
    Interval,
    MembershipStatus,
)
from apps.notifications import events

# Fields carried over verbatim into the next cycle.
COPIED_FIELDS = (
    "name", "description", "purpose", "target_amount", "is_recurring", "recurrence_interval", "admin",
    "payout_type", "allow_partial_payout", "bill_service_id", "bill_customer_id", "bill_variation",
    "recipient_bank_code", "recipient_bank_name", "recipient_account_name", "recipient_account_number",
    "series_anchor_date",
)


def due_date_for_cycle(group: ContributionGroup, cycle_number: int) -> date:
    """Cycle n is due `(n-1)` intervals after the series anchor.

    Offsetting from the anchor (rather than the previous due date) keeps the day-of-month stable:
    a group anchored on 31 Jan lands on 28 Feb, then 31 Mar, not 28 Feb -> 28 Mar -> 28 Apr.
    """
    step = Interval(group.recurrence_interval).months
    return group.series_anchor_date + relativedelta(months=step * (cycle_number - 1))


@transaction.atomic
def spawn_next_cycle(group: ContributionGroup) -> ContributionGroup | None:
    """Create the successor of `group` with the same members and split. Returns None if not applicable.

    Idempotent: `previous_cycle` is a OneToOne, so a group can have at most one successor even if
    this runs twice concurrently (the loser raises IntegrityError and rolls back).
    """
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    if not group.is_recurring or not group.recurrence_interval or group.status == GroupStatus.CANCELLED:
        return None
    if ContributionGroup.objects.filter(previous_cycle=group).exists():
        return None

    cycle = group.cycle_number + 1
    new_group = ContributionGroup(
        **{field: getattr(group, field) for field in COPIED_FIELDS},
        previous_cycle=group,
        cycle_number=cycle,
        status=GroupStatus.OPEN,
        due_date=due_date_for_cycle(group, cycle),
    )
    new_group.save()

    now = timezone.now()
    for m in group.memberships.exclude(status=MembershipStatus.LEFT):
        GroupMembership.objects.create(
            group=new_group, user_id=m.user_id, contribution_share=m.contribution_share,
            is_custom_share=m.is_custom_share, status=m.status,
            joined_at=now if m.status == MembershipStatus.JOINED else None,
        )
    events.cycle_opened(new_group)
    return new_group
