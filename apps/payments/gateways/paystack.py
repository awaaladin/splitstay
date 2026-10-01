import hashlib
import hmac
from decimal import Decimal

import requests
from django.conf import settings

from .base import (
    ChargeVerification,
    CheckoutSession,
    GatewayRejected,
    GatewayUnavailable,
    PaymentGateway,
    TransferResult,
    WebhookData,
)

TIMEOUT = 20


def to_kobo(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).to_integral_value())


def from_kobo(kobo) -> Decimal:
    return (Decimal(kobo) / 100).quantize(Decimal("0.01"))


class PaystackGateway(PaymentGateway):
    name = "paystack"

    def __init__(self, secret_key: str | None = None, base_url: str | None = None):
        self.secret = secret_key or settings.PAYSTACK_SECRET_KEY
        self.base = (base_url or settings.PAYSTACK_BASE_URL).rstrip("/")

    # -- http ---------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = requests.request(
                method, f"{self.base}{path}", headers={"Authorization": f"Bearer {self.secret}"},
                timeout=TIMEOUT, **kwargs,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GatewayUnavailable(f"Paystack unreachable: {exc}") from exc
        if response.status_code >= 500:
            raise GatewayUnavailable(f"Paystack error {response.status_code}")
        if not response.ok or not body.get("status"):
            raise GatewayRejected(body.get("message", f"Paystack error {response.status_code}"))
        return body["data"]

    # -- collection -----------------------------------------------------------
    def initialize_payment(self, *, reference, amount, email, callback_url, metadata=None):
        data = self._request("POST", "/transaction/initialize", json={
            "email": email, "amount": to_kobo(amount), "reference": reference,
            "callback_url": callback_url, "currency": "NGN", "metadata": metadata or {},
        })
        return CheckoutSession(url=data["authorization_url"], gateway_reference=data.get("access_code", ""))

    def verify_payment(self, reference):
        data = self._request("GET", f"/transaction/verify/{reference}")
        status = {"success": "success", "failed": "failed", "abandoned": "failed"}.get(data["status"], "pending")
        return ChargeVerification(status=status, amount=from_kobo(data["amount"]), gateway_reference=str(data.get("id", "")))

    # -- webhooks ---------------------------------------------------------------
    def verify_webhook_signature(self, raw_body, headers):
        signature = headers.get("x-paystack-signature", "")
        expected = hmac.new(self.secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return bool(signature) and hmac.compare_digest(signature, expected)

    def parse_webhook(self, payload):
        event = payload.get("event", "")
        data = payload.get("data") or {}
        kind = {
            "charge.success": "charge.success",
            "transfer.success": "transfer.success",
            "transfer.failed": "transfer.failed",
            "transfer.reversed": "transfer.failed",
        }.get(event, "other")
        reference = data.get("reference", "")
        # Paystack has no stable event id, so identity = event type + the object it is about.
        event_id = f"{event}:{data.get('id') or reference}"
        amount = from_kobo(data["amount"]) if data.get("amount") is not None else None
        return WebhookData(event_id=event_id, kind=kind, reference=reference, amount=amount,
                           gateway_reference=str(data.get("id", "")), raw=payload)

    # -- disbursement ---------------------------------------------------------------
    def initiate_transfer(self, *, reference, amount, account_number, bank_code, account_name, narration):
        recipient = self._request("POST", "/transferrecipient", json={
            "type": "nuban", "name": account_name, "account_number": account_number,
            "bank_code": bank_code, "currency": "NGN",
        })
        data = self._request("POST", "/transfer", json={
            "source": "balance", "amount": to_kobo(amount), "recipient": recipient["recipient_code"],
            "reason": narration[:100], "reference": reference,
        })
        status = {"success": "success", "failed": "failed", "reversed": "failed"}.get(data["status"], "pending")
        return TransferResult(status=status, gateway_reference=data.get("transfer_code", ""))

    def verify_transfer(self, reference):
        data = self._request("GET", f"/transfer/verify/{reference}")
        status = {"success": "success", "failed": "failed", "reversed": "failed"}.get(data["status"], "pending")
        return TransferResult(status=status, gateway_reference=data.get("transfer_code", ""))
