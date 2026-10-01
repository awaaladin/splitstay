from django.db.models import Q

from .models import ContributionGroup, GroupMembership, MembershipStatus


def groups_visible_to(user):
    """Groups the user administers or has been invited to / joined."""
    return (
        ContributionGroup.objects.filter(
            Q(admin=user)
            | Q(
                memberships__user=user,
                memberships__status__in=(MembershipStatus.INVITED, MembershipStatus.JOINED),
            )
        )
        .select_related("admin", "admin__profile")
        .distinct()
    )


def is_member(group: ContributionGroup, user) -> bool:
    """A 'member' is the admin or anyone who has joined. Invitees see the group but not its history."""
    if not user.is_authenticated:
        return False
    if group.admin_id == user.pk:
        return True
    return GroupMembership.objects.filter(group=group, user=user, status=MembershipStatus.JOINED).exists()


def get_membership(group: ContributionGroup, user):
    return GroupMembership.objects.filter(
        group=group, user=user, status__in=(MembershipStatus.INVITED, MembershipStatus.JOINED)
    ).first()


def active_memberships(group: ContributionGroup):
    return group.memberships.filter(
        status__in=(MembershipStatus.INVITED, MembershipStatus.JOINED)
    ).select_related("user", "user__profile")
