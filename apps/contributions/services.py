from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.groups.models import ContributionGroup, MembershipStatus

from .models import Contribution, ContributionStatus

PENDING_REUSE_WINDOW = timedelta(minutes=30)


@transaction.atomic
def initiate_contribution(group: ContributionGroup, user, amount=None) -> Contribution:
    """Create (or reuse) a pending contribution for `user` toward their own share.

    A member can only ever pay their own share: the caller passes the requesting user,
    never a different member. Amount defaults to whatever they still owe.
    """
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    if not group.is_open_for_contributions:
        raise ValidationError(f"This group is {group.get_status_display().lower()} and is not accepting contributions.")
    membership = group.memberships.filter(user=user, status=MembershipStatus.JOINED).first()
    if membership is None:
        raise ValidationError("Only joined members can contribute. Accept the invitation first.")

    outstanding = membership.outstanding
    if outstanding <= 0:
        raise ValidationError("You have already paid your full share.")
    amount = outstanding if amount is None else Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValidationError("Amount must be more than zero.")
    if amount > outstanding:
        raise ValidationError(f"That is more than your outstanding share of ₦{outstanding:,.2f}.")

    # Re-clicking "Pay" shouldn't leave a trail of duplicate pending rows.
    existing = (
        Contribution.objects.filter(
            group=group,
            member=user,
            status=ContributionStatus.PENDING,
            amount=amount,
            created_at__gte=timezone.now() - PENDING_REUSE_WINDOW,
        )
        .order_by("-created_at")
        .first()
    )
    if existing:
        return existing
    return Contribution.objects.create(group=group, member=user, amount=amount)
