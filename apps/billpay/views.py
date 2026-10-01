from dataclasses import asdict

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.groups.models import MembershipStatus

from . import catalog, services
from .models import BillPayment
from .providers import BillProviderUnavailable
from .serializers import BillerSerializer, BillPaymentSerializer, ValidateMeterSerializer


class BillPaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BillPaymentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return BillPayment.objects.none()
        user = self.request.user
        visible = Q(group__admin=user) | Q(
            group__memberships__user=user, group__memberships__status=MembershipStatus.JOINED
        )
        qs = BillPayment.objects.filter(visible).prefetch_related("fees").distinct()
        if self.request.query_params.get("group"):
            qs = qs.filter(group_id=self.request.query_params["group"])
        return qs


class BillerListView(APIView):
    @extend_schema(responses=BillerSerializer(many=True))
    def get(self, request):
        return Response([asdict(b) for b in catalog.BILLERS.values()])


class ValidateMeterView(APIView):
    @extend_schema(request=ValidateMeterSerializer, responses={200: dict})
    def post(self, request):
        serializer = ValidateMeterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if catalog.get_biller(data["service_id"]) is None:
            return Response({"detail": "Unknown biller."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            info = services.validate_meter(data["service_id"], data["customer_id"], data["variation"])
        except BillProviderUnavailable:
            return Response({"detail": "The biller could not be reached. Try again."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(asdict(info))
