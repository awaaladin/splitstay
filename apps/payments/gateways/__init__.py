from django.conf import settings

from .base import GatewayError, GatewayRejected, GatewayUnavailable, PaymentGateway  # noqa: F401
from .mock import MockGateway
from .paystack import PaystackGateway

_REGISTRY = {"paystack": PaystackGateway, "mock": MockGateway}


def get_gateway(name: str | None = None) -> PaymentGateway:
    name = name or settings.PAYMENT_GATEWAY
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(f"Unknown payment gateway '{name}'") from None
