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


KOBO = Decimal("0.01")


def fees_on_top() -> bool:
    return settings.SERVICE_FEE_MODE == "on_top"


def rate_for_pot(pot: Decimal | None) -> Decimal:
    """The percentage for a group of this target. Each tier's limit is inclusive; without tiers, the flat setting."""
    tiers = settings.SERVICE_FEE_TIERS
    if not tiers:
        return Decimal(settings.SERVICE_FEE_PERCENT)
    if pot is None:
        return tiers[0][1]
    for limit, rate in tiers:
        if limit is None or Decimal(pot) <= limit:
            return rate
    return tiers[-1][1]


def _policy_fee(base: Decimal, pot: Decimal | None = None) -> FeeQuote:
    """The configured fee for `base` (a whole pool in deduct mode, one member's payment in on_top mode)."""
    kind = settings.SERVICE_FEE_TYPE
    if kind == "percent":
        rate = rate_for_pot(pot)
        amount = (base * rate / 100).quantize(KOBO, rounding=ROUND_HALF_UP)
        minimum, maximum = Decimal(settings.SERVICE_FEE_MIN), Decimal(settings.SERVICE_FEE_MAX)
        if minimum:
            amount = max(amount, minimum)
        if maximum:
            amount = min(amount, maximum)
    else:
        kind = "flat"
        rate = Decimal(settings.SERVICE_FEE_FLAT)
        amount = rate.quantize(KOBO)
    return FeeQuote(fee_type=kind, rate=rate, amount=amount)


def fee_for_payment(amount: Decimal, pot: Decimal | None = None) -> FeeQuote:
    """The fee ADDED to one member's payment of `amount` toward a group targeting `pot` (zero in deduct mode)."""
    if not fees_on_top():
        return FeeQuote(fee_type=settings.SERVICE_FEE_TYPE, rate=Decimal("0"), amount=Decimal("0.00"))
    quote = _policy_fee(Decimal(amount), pot)
    return FeeQuote(quote.fee_type, quote.rate, quote.amount + Decimal(settings.SERVICE_FEE_PER_PAYMENT))


def quote_fee(gross: Decimal) -> FeeQuote:
    """The fee taken out of a payout of `gross`. In on_top mode the fee was already paid on top of each
    contribution, so nothing is deducted and the recipient receives the whole pool."""
    gross = Decimal(gross)
    if fees_on_top():
        return FeeQuote(fee_type=settings.SERVICE_FEE_TYPE, rate=Decimal("0"), amount=Decimal("0.00"))
    quote = _policy_fee(gross)
    if quote.amount >= gross:
        raise ValidationError(
            f"The pooled amount (₦{gross:,.2f}) does not cover the service fee (₦{quote.amount:,.2f})."
        )
    return quote
