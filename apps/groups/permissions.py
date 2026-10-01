from rest_framework.permissions import BasePermission

from . import selectors


class IsGroupMember(BasePermission):
    """Admin or joined member. Applied to history-bearing endpoints (ledger, contributions)."""

    message = "Only members of this group can do that."

    def has_object_permission(self, request, view, obj):
        return selectors.is_member(obj, request.user)


class IsGroupAdmin(BasePermission):
    message = "Only the group admin can do that."

    def has_object_permission(self, request, view, obj):
        return obj.admin_id == request.user.pk
