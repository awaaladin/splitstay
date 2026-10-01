import re
from decimal import Decimal

import requests
from django.conf import settings

from .base import BillProvider, BillProviderUnavailable, BillResult, CustomerInfo

TIMEOUT = 45  # electricity purchases can be slow


class VTpassProvider(BillProvider):
    name = "vtpass"

    def __init__(self):
        self.base = settings.VTPASS_BASE_URL.rstrip("/")
        self.headers = {"api-key": settings.VTPASS_API_KEY, "secret-key": settings.VTPASS_SECRET_KEY}

    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = requests.post(f"{self.base}{path}", json=payload, headers=self.headers, timeout=TIMEOUT)
            if response.status_code >= 500:
                raise BillProviderUnavailable(f"VTpass {response.status_code}")
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise BillProviderUnavailable(str(exc)) from exc

    def validate_customer(self, *, service_id, customer_id, variation):
        body = self._post("/merchant-verify", {"billersCode": customer_id, "serviceID": service_id, "type": variation})
        content = body.get("content") or {}
        if body.get("code") != "000" or content.get("error"):
            return CustomerInfo(False, message=content.get("error") or body.get("response_description", "Invalid meter"))
        return CustomerInfo(True, name=content.get("Customer_Name", ""), address=content.get("Address", ""))

    def pay(self, *, request_id, service_id, customer_id, amount, variation, phone):
        body = self._post("/pay", {
            "request_id": request_id, "serviceID": service_id, "billersCode": customer_id,
            "variation_code": variation, "amount": int(Decimal(amount)), "phone": phone,
        })
        return self._parse(body)

    def requery(self, request_id):
        return self._parse(self._post("/requery", {"request_id": request_id}))

    @staticmethod
    def _parse(body: dict) -> BillResult:
        txn = (body.get("content") or {}).get("transactions") or {}
        state = (txn.get("status") or "").lower()
        if body.get("code") == "000" and state == "delivered":
            status = "success"
        elif state in ("failed", "reversed", "rejected") or body.get("code") in ("016", "017", "018"):
            status = "failed"
        else:
            status = "pending"  # includes "pending"/"initiated"/"processing" and any unrecognised state
        # VTpass prints the token as "Token : 1234-5678-..."; keep just the digits/dashes.
        token = re.sub(r"^\s*Token\s*:\s*", "", str(body.get("purchased_code") or body.get("token") or "")).strip()
        return BillResult(
            status=status,
            provider_reference=str(txn.get("transactionId", "")),
            token=token,
            units=str(body.get("units", "")),
            customer_name=str(body.get("customerName", "")),
            message=body.get("response_description", ""),
            raw=body,
        )
