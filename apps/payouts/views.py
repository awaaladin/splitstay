from django.db.models import Q
from rest_framework import mixins, viewsets

from apps.groups.models import MembershipStatus

from .models import Payout
from .serializers import PayoutSerializer


class PayoutViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Bank-transfer payouts for groups the requester belongs to."""

    serializer_class = PayoutSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payout.objects.none()
        user = self.request.user
        visible = Q(group__admin=user) | Q(
            group__memberships__user=user, group__memberships__status=MembershipStatus.JOINED
        )
        qs = Payout.objects.filter(visible).prefetch_related("fees").distinct()
        if self.request.query_params.get("group"):
            qs = qs.filter(group_id=self.request.query_params["group"])
        return qs
