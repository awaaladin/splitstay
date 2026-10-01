"""Domain events -> notifications. The rest of the codebase calls these; wording lives in one place."""
from .models import Kind
from .services import notify


def naira(amount) -> str:
    return f"₦{amount:,.2f}"


def _audience(group):
    """Admin plus every joined member, deduplicated."""
    users = {group.admin_id: group.admin}
    for membership in group.memberships.filter(status="joined").select_related("user"):
        users[membership.user_id] = membership.user
    return users.values()


def member_invited(membership):
    group = membership.group
    notify(
        membership.user, Kind.INVITED, f"You were invited to {group.name}",
        f"{group.admin.display_name} invited you. Your share is {naira(membership.contribution_share)}.",
        group=group, dedupe_key=f"invited:{group.pk}:{membership.user_id}:{int(membership.invited_at.timestamp())}",
    )


def contribution_received(contribution):
    group, payer = contribution.group, contribution.member
    for user in _audience(group):
        if user.pk == payer.pk:
            notify(user, Kind.CONTRIBUTION, "Payment received",
                   f"Your {naira(contribution.amount)} for {group.name} was confirmed.",
                   group=group, dedupe_key=f"contrib:{contribution.pk}:{user.pk}")
        else:
            notify(user, Kind.CONTRIBUTION, f"{payer.display_name} contributed",
                   f"{payer.display_name} paid {naira(contribution.amount)} toward {group.name}.",
                   group=group, dedupe_key=f"contrib:{contribution.pk}:{user.pk}")


def group_funded(group):
    for user in _audience(group):
        notify(user, Kind.FUNDED, f"{group.name} is fully funded",
               f"The target of {naira(group.target_amount)} has been reached. Payment is being processed.",
               group=group, dedupe_key=f"funded:{group.pk}:{user.pk}")


def group_overdue(group):
    for user in _audience(group):
        notify(user, Kind.OVERDUE, f"{group.name} is overdue",
               f"The due date passed on {group.due_date:%d %b %Y} and the target has not been reached.",
               group=group, dedupe_key=f"overdue:{group.pk}:{user.pk}")


def payout_completed(group, record):
    what = "The bill was paid" if hasattr(record, "service_id") else "The transfer was sent"
    for user in _audience(group):
        notify(user, Kind.PAYOUT_DONE, f"{group.name}: payment complete",
               f"{what} ({naira(record.net_amount)} after a {naira(record.fee_amount)} service fee). "
               "The receipt is on the group page.",
               group=group, dedupe_key=f"payout_done:{record.reference}:{user.pk}")


def payout_failed(group, record):
    for user in _audience(group):
        notify(user, Kind.PAYOUT_FAILED, f"{group.name}: payment failed",
               f"{record.failure_reason or 'The payment could not be completed'}. "
               "The group admin can retry from the group page.",
               group=group, dedupe_key=f"payout_failed:{record.reference}:{user.pk}")


def due_reminder(group, user, days_left, outstanding):
    when = "today" if days_left == 0 else "tomorrow" if days_left == 1 else f"in {days_left} days"
    notify(user, Kind.REMINDER, f"{group.name} is due {when}",
           f"You still owe {naira(outstanding)}.", group=group,
           dedupe_key=f"reminder:{group.pk}:{user.pk}:{days_left}")


def cycle_opened(group):
    for user in _audience(group):
        notify(user, Kind.CYCLE, f"{group.name}: new cycle opened",
               f"Cycle {group.cycle_number} is due {group.due_date:%d %b %Y}. Your share is unchanged.",
               group=group, dedupe_key=f"cycle:{group.pk}:{user.pk}")
