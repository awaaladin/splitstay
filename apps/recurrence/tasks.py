import logging
from datetime import date

from celery import shared_task
from django.db import IntegrityError
from django.db.models import Q

from apps.groups.models import ContributionGroup, GroupStatus

from .services import spawn_next_cycle

log = logging.getLogger(__name__)


@shared_task
def spawn_due_cycles(today: date | None = None) -> int:
    """Open the next cycle for every recurring group that is paid out or past its due date."""
    today = today or date.today()
    candidates = (
        ContributionGroup.objects.filter(is_recurring=True, next_cycle__isnull=True)
        .exclude(status=GroupStatus.CANCELLED)
        .filter(Q(status=GroupStatus.PAID_OUT) | Q(due_date__lt=today))
    )
    created = 0
    for group in candidates:
        try:
            if spawn_next_cycle(group):
                created += 1
        except IntegrityError:
            log.info("Cycle for group %s was created concurrently", group.pk)
    return created
