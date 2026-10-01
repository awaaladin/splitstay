"""Offline provider for dev/tests. Meter numbers ending in 9999 are rejected so failures can be exercised."""
import hashlib
from decimal import Decimal

from .base import BillProvider, BillResult, CustomerInfo


class MockBillProvider(BillProvider):
    name = "mock"

    def validate_customer(self, *, service_id, customer_id, variation):
        if not customer_id.isdigit() or len(customer_id) < 6 or customer_id.endswith("9999"):
            return CustomerInfo(False, message="Meter not found")
        return CustomerInfo(True, name="DEMO CUSTOMER", address="12 Demo Street, Lagos")

    def pay(self, *, request_id, service_id, customer_id, amount, variation, phone):
        if customer_id.endswith("9999"):
            return BillResult("failed", message="Meter rejected by disco")
        return self._success(request_id, Decimal(amount), variation)

    def requery(self, request_id):
        return BillResult("pending", message="Unknown to mock provider")

    @staticmethod
    def _success(request_id, amount, variation):
        digits = "".join(str(int(c, 16) % 10) for c in hashlib.sha256(request_id.encode()).hexdigest()[:20])
        token = "-".join(digits[i:i + 4] for i in range(0, 20, 4)) if variation != "postpaid" else ""
        return BillResult(
            "success", provider_reference=f"MOCK{digits[:10]}", token=token,
            units=f"{amount / Decimal('68'):.1f} kWh", customer_name="DEMO CUSTOMER", message="Delivered",
        )
