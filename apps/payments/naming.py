"""How SplitPay labels its money on the shared Paystack account.

One Paystack account serves several apps, so every reference starts with the app code and
every transaction carries the same metadata keys. That lets the dashboard, exports and the
webhook router tell SplitPay's payments apart from the other apps':

    SPLITPAY-CONTRIB-20261023-4F9A2C7B1E0D   member contribution (collection)
    splitpay-payout-20261023-9c1e...          transfer to a group's recipient (Paystack
                                               transfer references must be lowercase)
"""
import uuid

from django.utils import timezone

APP_CODE = "SPLITPAY"
APP_NAME = "SplitPay"


def make_reference(purpose: str, *, length: int = 12) -> str:
    stamp = timezone.now().strftime("%Y%m%d")
    return f"{APP_CODE}-{purpose.upper()}-{stamp}-{uuid.uuid4().hex[:length].upper()}"


def make_transfer_reference(purpose: str, *, length: int = 16) -> str:
    return make_reference(purpose, length=length).lower()


def is_ours(reference: str, metadata=None) -> bool:
    """True only for this app's own transactions on the shared account.

    metadata.app, when present, must say SPLITPAY; the reference must start with our code. Either
    one pointing at another app (or nothing at all) means the event is not ours and is ignored.
    """
    if isinstance(metadata, dict) and metadata.get("app") and str(metadata["app"]).upper() != APP_CODE:
        return False
    return (reference or "").upper().startswith(f"{APP_CODE}-")


def paystack_metadata(purpose: str, description: str, **extra) -> dict:
    """Metadata sent with every transaction. custom_fields show on the Paystack dashboard."""
    return {
        "app": APP_CODE,
        "app_name": APP_NAME,
        "purpose": purpose.upper(),
        **extra,
        "custom_fields": [
            {"display_name": "App", "variable_name": "app", "value": APP_NAME},
            {"display_name": "Payment for", "variable_name": "purpose", "value": description[:200]},
        ],
    }
