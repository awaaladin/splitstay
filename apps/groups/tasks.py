from datetime import date

from celery import shared_task
from django.db import transaction

from .models import ContributionGroup, GroupStatus


@shared_task
def enforce_deadlines(today: date | None = None) -> int:
    """Flip open groups whose due date has passed to 'overdue' and tell the members."""
    from apps.notifications import events

    today = today or date.today()
    count = 0
    for group_id in ContributionGroup.objects.filter(
        status=GroupStatus.OPEN, due_date__lt=today
    ).values_list("id", flat=True):
        with transaction.atomic():
            group = ContributionGroup.objects.select_for_update().get(pk=group_id)
            if group.status != GroupStatus.OPEN:
                continue
            group.status = GroupStatus.OVERDUE
            group.save(update_fields=["status", "updated_at"])
            events.group_overdue(group)
            count += 1
    return count
