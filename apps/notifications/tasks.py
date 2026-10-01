from datetime import date

from celery import shared_task

from apps.groups.models import ContributionGroup, GroupStatus, MembershipStatus

from . import events

REMINDER_DAYS = (7, 3, 1, 0)


@shared_task
def send_due_reminders(today: date | None = None) -> int:
    """Remind members who still owe money as the due date approaches (7, 3, 1 days and on the day).

    Each (group, member, day-offset) reminder has a dedupe key, so re-running the task is harmless.
    """
    today = today or date.today()
    sent = 0
    groups = ContributionGroup.objects.filter(
        status__in=(GroupStatus.OPEN, GroupStatus.OVERDUE),
        due_date__in=[today.fromordinal(today.toordinal() + d) for d in REMINDER_DAYS],
    )
    for group in groups:
        days_left = (group.due_date - today).days
        for membership in group.memberships.filter(status=MembershipStatus.JOINED).select_related("user"):
            outstanding = membership.outstanding
            if outstanding > 0:
                events.due_reminder(group, membership.user, days_left, outstanding)
                sent += 1
    return sent
