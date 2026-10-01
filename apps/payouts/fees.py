from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class FeeQuote:
    fee_type: str  # "flat" | "percent"
    rate: Decimal
    amount: Decimal

    def net(self, gross: Decimal) -> Decimal:
        return gross - self.amount


def quote_fee(gross: Decimal) -> FeeQuote:
    """Compute the service fee for a payout of `gross` from the configured policy."""
    gross = Decimal(gross)
    kind = settings.SERVICE_FEE_TYPE
    if kind == "percent":
        rate = Decimal(settings.SERVICE_FEE_PERCENT)
        amount = (gross * rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        minimum, maximum = Decimal(settings.SERVICE_FEE_MIN), Decimal(settings.SERVICE_FEE_MAX)
        if minimum:
            amount = max(amount, minimum)
        if maximum:
            amount = min(amount, maximum)
    else:
        kind = "flat"
        rate = Decimal(settings.SERVICE_FEE_FLAT)
        amount = rate.quantize(Decimal("0.01"))
    if amount >= gross:
        raise ValidationError(
            f"The pooled amount (₦{gross:,.2f}) does not cover the service fee (₦{amount:,.2f})."
        )
    return FeeQuote(fee_type=kind, rate=rate, amount=amount)
