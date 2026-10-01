from django.conf import settings

from .base import BillProvider, BillProviderUnavailable, BillResult, CustomerInfo  # noqa: F401
from .mock import MockBillProvider
from .vtpass import VTpassProvider

_REGISTRY = {"vtpass": VTpassProvider, "mock": MockBillProvider}


def get_provider(name: str | None = None) -> BillProvider:
    name = name or settings.BILL_PROVIDER
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(f"Unknown bill provider '{name}'") from None
