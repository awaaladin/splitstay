from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class CustomerInfo:
    valid: bool
    name: str = ""
    address: str = ""
    message: str = ""


@dataclass
class BillResult:
    status: str  # "success" | "failed" | "pending"
    provider_reference: str = ""
    token: str = ""
    units: str = ""
    customer_name: str = ""
    message: str = ""
    raw: dict = field(default_factory=dict)


class BillProviderUnavailable(Exception):
    """Timeout / 5xx: the purchase may or may not have happened. Callers must reconcile, not retry blindly."""


class BillProvider(ABC):
    """A bill-payment backend. Concrete providers implement these three calls for any biller category."""

    name: str

    @abstractmethod
    def validate_customer(self, *, service_id: str, customer_id: str, variation: str) -> CustomerInfo: ...

    @abstractmethod
    def pay(self, *, request_id: str, service_id: str, customer_id: str, amount: Decimal,
            variation: str, phone: str) -> BillResult: ...

    @abstractmethod
    def requery(self, request_id: str) -> BillResult: ...
