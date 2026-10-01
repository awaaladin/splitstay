from dataclasses import asdict

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.pagination import StandardPagination
from apps.contributions.models import Contribution
from apps.groups import selectors
from apps.groups.models import ContributionGroup
from apps.groups.permissions import IsGroupMember

from . import services
from .serializers import LedgerEntrySerializer


def paginated_group_ledger(view, request, group):
    """Shared by /ledger/groups/<id>/ and /groups/<id>/ledger/. Caller has already checked membership."""
    paginator = StandardPagination()
    page = paginator.paginate_queryset(services.group_entries(group), request, view=view)
    response = paginator.get_paginated_response(LedgerEntrySerializer([asdict(e) for e in page], many=True).data)
    response.data["summary"] = services.group_summary(group)
    response.data["members"] = [
        {"user_id": r["user"].pk, "name": r["user"].display_name, "share": r["share"], "paid": r["paid"],
         "outstanding": r["outstanding"], "state": r["state"]}
        for r in services.member_rows(group)
    ]
    return response


class GroupLedgerView(APIView):
    """Full history of one group. Visible to every member, not only the admin."""

    permission_classes = [IsGroupMember]

    @extend_schema(responses=LedgerEntrySerializer(many=True))
    def get(self, request, group_id):
        group = get_object_or_404(ContributionGroup, pk=group_id)
        self.check_object_permissions(request, group)
        return paginated_group_ledger(self, request, group)


class MyLedgerView(APIView):
    """The requester's own contribution history across every group."""

    @extend_schema(responses=LedgerEntrySerializer(many=True))
    def get(self, request):
        rows = Contribution.objects.filter(member=request.user).exclude(status="pending").select_related("group")
        entries = [
            {"at": c.paid_at or c.created_at, "kind": "contribution", "title": c.group.name, "amount": c.amount,
             "status": c.status, "actor": request.user.display_name, "reference": c.reference,
             "detail": {"group_id": c.group_id}}
            for c in rows.order_by("-created_at")
        ]
        paginator = StandardPagination()
        page = paginator.paginate_queryset(entries, request, view=self)
        return paginator.get_paginated_response(LedgerEntrySerializer(page, many=True).data)
