"""Offline gateway for local development and tests. Never allowed in production settings."""
from decimal import Decimal

from django.conf import settings
from django.urls import reverse

from .base import ChargeVerification, CheckoutSession, PaymentGateway, TransferResult, WebhookData


class MockGateway(PaymentGateway):
    name = "mock"

    def initialize_payment(self, *, reference, amount, email, callback_url, metadata=None):
        url = settings.SITE_URL.rstrip("/") + reverse("web:mock_checkout", args=[reference])
        return CheckoutSession(url=url, gateway_reference=f"mock-{reference}")

    def verify_payment(self, reference):
        from apps.contributions.models import Contribution

        contribution = Contribution.objects.filter(reference=reference).first()
        if contribution and contribution.status == "paid":
            return ChargeVerification("success", contribution.amount, f"mock-{reference}")
        return ChargeVerification("pending")

    def verify_webhook_signature(self, raw_body, headers):
        return False  # the mock gateway has no webhooks; the checkout page confirms directly

    def parse_webhook(self, payload):
        return WebhookData(event_id="", kind="other")

    def initiate_transfer(self, *, reference, amount, account_number, bank_code, account_name, narration):
        return TransferResult("success", f"mock-{reference}")

    def verify_transfer(self, reference):
        return TransferResult("success", f"mock-{reference}")
