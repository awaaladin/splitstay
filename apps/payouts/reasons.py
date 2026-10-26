"""Human wording for payout failures that are about SplitPay's own payment account, not the group.

Kept free of imports so both payouts.services and notifications.events can use it.
"""
PLATFORM_DELAY = (
    "Payouts are still being switched on for SplitPay's payment account. "
    "Your money is safe and will be sent as soon as that is done"
)
PLATFORM_FUNDS = "SplitPay's payment account is being topped up. Your money is safe and the payout will be retried"
PLATFORM_REASONS = (PLATFORM_DELAY, PLATFORM_FUNDS)


def friendly_failure_reason(message: str) -> str:
    """Turn a raw gateway refusal into something a group member should read."""
    lowered = (message or "").lower()
    if "starter business" in lowered or "third party payouts" in lowered:
        return PLATFORM_DELAY
    if "balance is not enough" in lowered or "insufficient" in lowered:
        return PLATFORM_FUNDS
    return message
