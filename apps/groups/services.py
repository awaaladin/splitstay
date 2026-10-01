"""Group and membership business rules. Views (API and web) call these; they never re-implement them."""
from decimal import ROUND_DOWN, Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.phone import normalize_phone

from .models import (
    ContributionGroup,
    GroupMembership,
    GroupStatus,
    MembershipStatus,
    PayoutType,
)

User = get_user_model()
KOBO = Decimal("0.01")
ACTIVE = (MembershipStatus.INVITED, MembershipStatus.JOINED)


def money(value) -> Decimal:
    return Decimal(value).quantize(KOBO)


# --- Share allocation -------------------------------------------------------

def rebalance_shares(group: ContributionGroup) -> None:
    """Spread (target - custom shares) equally across non-custom members, to the kobo.

    Any leftover kobo goes one-by-one to the earliest members, so shares always sum
    exactly to the target when at least one member has an equal share.
    """
    members = list(group.memberships.filter(status__in=ACTIVE).order_by("id"))
    custom_total = sum((m.contribution_share for m in members if m.is_custom_share), Decimal("0"))
    equal = [m for m in members if not m.is_custom_share]
    remaining = group.target_amount - custom_total
    if remaining < 0:
        raise ValidationError("Custom shares add up to more than the target amount.")
    if not equal:
        if members and remaining != 0:
            raise ValidationError("With every share set by hand, shares must add up to the target amount.")
        return
    base = (remaining / len(equal)).quantize(KOBO, rounding=ROUND_DOWN)
    leftover_kobo = int((remaining - base * len(equal)) / KOBO)
    for index, member in enumerate(equal):
        member.contribution_share = base + (KOBO if index < leftover_kobo else Decimal("0"))
        member.save(update_fields=["contribution_share"])


def assert_shares_editable(group: ContributionGroup) -> None:
    if not group.is_open_for_contributions:
        raise ValidationError("This group is closed; members and shares can no longer change.")
    if group.contributions.filter(status="paid").exists():
        raise ValidationError(
            "Contributions have already been received, so members and shares are locked to keep every "
            "payment consistent with what each person owes."
        )


# --- Group lifecycle ---------------------------------------------------------

@transaction.atomic
def create_group(*, admin, members=(), **fields) -> ContributionGroup:
    """`members` is an iterable of (user, share_or_None). The admin is added automatically."""
    fields.setdefault("series_anchor_date", fields["due_date"])
    group = ContributionGroup(admin=admin, **fields)
    group.full_clean(exclude=["admin"])
    group.save()
    now = timezone.now()
    GroupMembership.objects.create(group=group, user=admin, status=MembershipStatus.JOINED, joined_at=now)
    for user, share in members:
        if user.pk == admin.pk:
            continue
        _add_membership(group, user, share)
    rebalance_shares(group)
    from apps.notifications import events

    for membership in group.memberships.filter(status=MembershipStatus.INVITED):
        events.member_invited(membership)
    return group


def _add_membership(group, user, share=None) -> GroupMembership:
    membership, created = GroupMembership.objects.get_or_create(group=group, user=user)
    if not created and membership.status != MembershipStatus.LEFT:
        raise ValidationError(f"{user.display_name} is already in this group.")
    membership.status = MembershipStatus.INVITED
    membership.joined_at = None
    if share is not None:
        membership.contribution_share = money(share)
        membership.is_custom_share = True
    else:
        membership.is_custom_share = False
    membership.save()
    return membership


def find_user(identifier: str):
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if "@" in identifier:
        return User.objects.filter(email__iexact=identifier).first()
    return User.objects.filter(profile__phone_number=normalize_phone(identifier)).first()


@transaction.atomic
def add_member(group: ContributionGroup, user, share=None) -> GroupMembership:
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    assert_shares_editable(group)
    membership = _add_membership(group, user, share)
    rebalance_shares(group)
    membership.refresh_from_db()
    from apps.notifications import events

    events.member_invited(membership)
    return membership


@transaction.atomic
def remove_member(group: ContributionGroup, user) -> None:
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    if user.pk == group.admin_id:
        raise ValidationError("The group admin cannot be removed.")
    membership = group.memberships.filter(user=user, status__in=ACTIVE).first()
    if membership is None:
        raise ValidationError("That person is not an active member.")
    if group.contributions.filter(member=user, status="paid").exists():
        raise ValidationError("This member has already contributed and cannot be removed.")
    assert_shares_editable(group)
    membership.status = MembershipStatus.LEFT
    membership.is_custom_share = False
    membership.contribution_share = Decimal("0.00")
    membership.save()
    rebalance_shares(group)


@transaction.atomic
def set_member_share(group: ContributionGroup, user, share) -> GroupMembership:
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    assert_shares_editable(group)
    membership = group.memberships.filter(user=user, status__in=ACTIVE).first()
    if membership is None:
        raise ValidationError("That person is not an active member.")
    if share is None:
        membership.is_custom_share = False
    else:
        share = money(share)
        if share <= 0:
            raise ValidationError("A share must be more than zero.")
        membership.contribution_share = share
        membership.is_custom_share = True
    membership.save()
    rebalance_shares(group)
    membership.refresh_from_db()
    return membership


@transaction.atomic
def accept_invitation(group: ContributionGroup, user) -> GroupMembership:
    membership = group.memberships.select_for_update().filter(user=user, status=MembershipStatus.INVITED).first()
    if membership is None:
        raise ValidationError("There is no pending invitation for you in this group.")
    membership.status = MembershipStatus.JOINED
    membership.joined_at = timezone.now()
    membership.save(update_fields=["status", "joined_at"])
    return membership


@transaction.atomic
def leave_group(group: ContributionGroup, user) -> None:
    """A member declines an invitation or leaves (only allowed before they have paid)."""
    if user.pk == group.admin_id:
        raise ValidationError("The admin cannot leave; cancel the group instead.")
    remove_member(group, user)


@transaction.atomic
def update_group(group: ContributionGroup, **changes) -> ContributionGroup:
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    if not group.is_open_for_contributions:
        raise ValidationError("A closed group can no longer be edited.")
    money_fields_changed = "target_amount" in changes and changes["target_amount"] != group.target_amount
    if money_fields_changed and group.contributions.filter(status="paid").exists():
        raise ValidationError("The target cannot change once contributions have been received.")
    if "payout_type" in changes and changes["payout_type"] != group.payout_type:
        if group.contributions.filter(status="paid").exists():
            raise ValidationError("The payout type cannot change once contributions have been received.")
    for key, value in changes.items():
        setattr(group, key, value)
    group.full_clean(exclude=["admin"])
    group.save()
    if money_fields_changed:
        rebalance_shares(group)
    return group


@transaction.atomic
def cancel_group(group: ContributionGroup) -> ContributionGroup:
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    if group.status in (GroupStatus.PAID_OUT, GroupStatus.CANCELLED):
        raise ValidationError(f"A {group.get_status_display().lower()} group cannot be cancelled.")
    if group.contributions.filter(status="paid").exists():
        raise ValidationError(
            "Contributions have already been received. Pay out the group instead of cancelling it."
        )
    group.status = GroupStatus.CANCELLED
    group.is_recurring = False
    group.save(update_fields=["status", "is_recurring", "updated_at"])
    group.contributions.filter(status="pending").update(status="failed")
    return group


def is_payout_type_ready(group: ContributionGroup) -> bool:
    if group.payout_type == PayoutType.BILL_PAYMENT:
        return bool(group.bill_service_id and group.bill_customer_id)
    return bool(group.recipient_bank_code and group.recipient_account_number)
