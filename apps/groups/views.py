from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.billpay.serializers import BillPaymentSerializer
from apps.contributions import services as contribution_services
from apps.contributions.selectors import progress
from apps.contributions.serializers import ContributeSerializer, ContributionSerializer
from apps.ledger.views import paginated_group_ledger
from apps.payments import services as payment_services
from apps.payments.gateways import GatewayError
from apps.payouts import services as payout_services
from apps.payouts.serializers import PayoutSerializer

from . import selectors, services
from .models import ContributionGroup, GroupStatus, PayoutType
from .permissions import IsGroupAdmin, IsGroupMember
from .serializers import GroupSerializer, GroupWriteSerializer, MemberInputSerializer, MembershipSerializer


class GroupViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Contribution groups. Deleting is not offered: cancel a group instead so history is preserved."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContributionGroup.objects.none()
        qs = selectors.groups_visible_to(self.request.user).order_by("-created_at")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def get_serializer_class(self):
        return GroupWriteSerializer if self.action in ("create", "partial_update", "update") else GroupSerializer

    def get_throttles(self):
        if self.action == "create":
            throttle = ScopedRateThrottle()
            throttle.scope = "group_create"
            return [throttle]
        return super().get_throttles()

    def get_permissions(self):
        admin_actions = {"partial_update", "update", "members", "member_detail", "payout", "cancel"}
        member_actions = {"ledger", "contribute"}
        if self.action in admin_actions:
            return [IsAuthenticated(), IsGroupAdmin()]
        if self.action in member_actions:
            return [IsAuthenticated(), IsGroupMember()]
        return [IsAuthenticated()]

    # -- create / update -------------------------------------------------------------
    @extend_schema(request=GroupWriteSerializer, responses={201: GroupSerializer})
    def create(self, request, *args, **kwargs):
        serializer = GroupWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        members = []
        for entry in request.data.get("members", []) or []:
            item = MemberInputSerializer(data=entry, context={})
            item.is_valid(raise_exception=True)
            members.append((item.context["resolved_user"], item.validated_data.get("contribution_share")))
        data.pop("members", None)
        number = data.pop("recipient_account_number", "")
        group = services.create_group(admin=request.user, members=members, recipient_account_number=number, **data)
        return Response(GroupSerializer(group, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=GroupWriteSerializer, responses=GroupSerializer)
    def partial_update(self, request, *args, **kwargs):
        group = self.get_object()
        serializer = GroupWriteSerializer(group, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        changes.pop("members", None)
        if "recipient_account_number" in changes:
            changes["recipient_account_number"] = changes["recipient_account_number"] or group.recipient_account_number
        group = services.update_group(group, **changes)
        return Response(GroupSerializer(group, context={"request": request}).data)

    # -- membership -------------------------------------------------------------------
    @extend_schema(request=MemberInputSerializer, responses=MembershipSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        group = self.get_object()
        if request.method == "GET":
            return Response(MembershipSerializer(selectors.active_memberships(group), many=True).data)
        serializer = MemberInputSerializer(data=request.data, context={})
        serializer.is_valid(raise_exception=True)
        membership = services.add_member(
            group, serializer.context["resolved_user"], serializer.validated_data.get("contribution_share")
        )
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=inline_serializer("SetShare", {"contribution_share": serializers.DecimalField(14, 2, allow_null=True)}),
        responses=MembershipSerializer,
    )
    @action(detail=True, methods=["patch", "delete"], url_path=r"members/(?P<user_id>\d+)", url_name="member-detail")
    def member_detail(self, request, pk=None, user_id=None):
        group = self.get_object()
        target = get_object_or_404(group.memberships.exclude(status="left"), user_id=user_id).user
        if request.method == "DELETE":
            services.remove_member(group, target)
            return Response(status=status.HTTP_204_NO_CONTENT)
        membership = services.set_member_share(group, target, request.data.get("contribution_share"))
        return Response(MembershipSerializer(membership).data)

    @extend_schema(request=None, responses=GroupSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        group = self.get_object()
        services.accept_invitation(group, request.user)
        return Response(GroupSerializer(group, context={"request": request}).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"], url_path="leave", url_name="leave")
    def leave(self, request, pk=None):
        """Decline an invitation or leave the group (before contributing)."""
        services.leave_group(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=GroupSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        group = services.cancel_group(self.get_object())
        return Response(GroupSerializer(group, context={"request": request}).data)

    # -- money ----------------------------------------------------------------------------
    @extend_schema(
        request=ContributeSerializer,
        responses={201: inline_serializer("ContributeResponse", {
            "contribution": ContributionSerializer(), "checkout_url": serializers.URLField()})},
    )
    @action(detail=True, methods=["post"])
    def contribute(self, request, pk=None):
        """Start paying the requester's own share. Returns a gateway checkout URL."""
        group = self.get_object()
        serializer = ContributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contribution = contribution_services.initiate_contribution(
            group, request.user, serializer.validated_data.get("amount")
        )
        try:
            url = payment_services.start_checkout(contribution)
        except GatewayError:
            return Response({"detail": "The payment gateway is unavailable. Try again shortly."},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response({"contribution": ContributionSerializer(contribution).data, "checkout_url": url},
                        status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: PayoutSerializer, 201: PayoutSerializer})
    @action(detail=True, methods=["post"])
    def payout(self, request, pk=None):
        """Admin: pay out now (if the group allows partial payout) or retry a failed payout."""
        group = self.get_object()
        record = payout_services.get_payout_record(group)
        if record is not None and record.status == "failed":
            record = payout_services.retry_payout(group)
        else:
            record = payout_services.request_payout(group, triggered_by=request.user, partial=True)
        serializer = BillPaymentSerializer if group.payout_type == PayoutType.BILL_PAYMENT else PayoutSerializer
        return Response(serializer(record).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        return Response(progress(self.get_object()))

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        """Every contribution, fee and payout outcome. Visible to all joined members."""
        return paginated_group_ledger(self, request, self.get_object())
