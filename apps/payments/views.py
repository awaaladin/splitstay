import json
import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contributions.models import Contribution
from apps.contributions.serializers import ContributionSerializer

from . import services
from .gateways import get_gateway

log = logging.getLogger(__name__)


class PaystackWebhookView(APIView):
    """Receives Paystack events. Authenticated by HMAC signature, not by user credentials."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []

    @extend_schema(request=None, responses={200: None}, auth=[])
    def post(self, request):
        raw = request.body
        gateway = get_gateway("paystack")
        if not gateway.verify_webhook_signature(raw, request.headers):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(raw)
        except ValueError:
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)
        outcome = services.process_webhook("paystack", raw, payload)
        return Response({"status": outcome})


class VerifyPaymentView(APIView):
    """A member asks us to check one of their own pending contributions with the gateway."""

    @extend_schema(request=None, responses=ContributionSerializer)
    def post(self, request, reference):
        contribution = Contribution.objects.filter(reference=reference, member=request.user).first()
        if contribution is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        contribution = services.verify_and_confirm(contribution)
        return Response(ContributionSerializer(contribution).data)
