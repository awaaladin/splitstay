from rest_framework import mixins, viewsets

from apps.groups.models import MembershipStatus

from .models import Contribution
from .serializers import ContributionSerializer


class ContributionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Contributions in groups the requester belongs to. Optional ?group=<id> and ?mine=1 filters."""

    serializer_class = ContributionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Contribution.objects.none()
        user = self.request.user
        # Only joined members (or the admin) can see a group's contribution history.
        from django.db.models import Q

        visible_groups = Q(group__admin=user) | Q(
            group__memberships__user=user, group__memberships__status=MembershipStatus.JOINED
        )
        qs = (
            Contribution.objects.filter(visible_groups)
            .select_related("member", "member__profile")
            .distinct()
            .order_by("-created_at")
        )
        params = self.request.query_params
        if params.get("group"):
            qs = qs.filter(group_id=params["group"])
        if params.get("mine") in {"1", "true"}:
            qs = qs.filter(member=user)
        return qs
