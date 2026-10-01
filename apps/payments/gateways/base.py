"""Gateway-agnostic interface. Add Flutterwave by implementing PaymentGateway and registering it."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


class GatewayError(Exception):
    """Base class for gateway failures."""


class GatewayRejected(GatewayError):
    """The gateway definitively refused the request. Nothing happened on their side."""


class GatewayUnavailable(GatewayError):
    """Network failure, timeout or 5xx. The outcome is UNKNOWN: never treat as a definite failure."""


@dataclass
class CheckoutSession:
    url: str
    gateway_reference: str = ""


@dataclass
class ChargeVerification:
    status: str  # "success" | "failed" | "pending"
    amount: Decimal | None = None
    gateway_reference: str = ""


@dataclass
class TransferResult:
    status: str  # "success" | "failed" | "pending"
    gateway_reference: str = ""
    message: str = ""


@dataclass
class WebhookData:
    event_id: str
    kind: str  # charge.success | charge.failed | transfer.success | transfer.failed | other
    reference: str = ""
    amount: Decimal | None = None
    gateway_reference: str = ""
    raw: dict = field(default_factory=dict)


class PaymentGateway(ABC):
    name: str

    @abstractmethod
    def initialize_payment(self, *, reference: str, amount: Decimal, email: str, callback_url: str,
                           metadata: dict | None = None) -> CheckoutSession: ...

    @abstractmethod
    def verify_payment(self, reference: str) -> ChargeVerification: ...

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, headers) -> bool: ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> WebhookData: ...

    @abstractmethod
    def initiate_transfer(self, *, reference: str, amount: Decimal, account_number: str, bank_code: str,
                          account_name: str, narration: str) -> TransferResult: ...

    @abstractmethod
    def verify_transfer(self, reference: str) -> TransferResult: ...
