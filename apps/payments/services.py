"""Collection-side money logic: checkout, confirmation, funding threshold, webhook dispatch.

Idempotency is enforced in two independent layers:
  1. WebhookEvent has a unique (provider, event_id): a re-delivered event is recognised and skipped.
  2. confirm_contribution() locks the contribution row and only ever moves it to PAID once, so even
     if two identical deliveries race past layer 1 the money is still counted exactly once.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.contributions.models import Contribution, ContributionStatus
from apps.contributions.selectors import total_funded
from apps.groups.models import ContributionGroup, GroupStatus
from apps.notifications import events

from .gateways import GatewayError, get_gateway
from .models import WebhookEvent

log = logging.getLogger(__name__)


@dataclass
class ConfirmResult:
    contribution: Contribution
    newly_confirmed: bool


# --- Checkout ---------------------------------------------------------------

def start_checkout(contribution: Contribution) -> str:
    """Return a gateway checkout URL for a pending contribution (reusing one if already created)."""
    if contribution.status != ContributionStatus.PENDING:
        raise ValueError("Only pending contributions can be checked out")
    if contribution.checkout_url:
        return contribution.checkout_url
    gateway = get_gateway()
    callback = settings.SITE_URL.rstrip("/") + reverse("web:payment_return")
    session = gateway.initialize_payment(
        reference=contribution.reference,
        amount=contribution.amount,
        email=contribution.member.email,
        callback_url=callback,
        metadata={"group_id": contribution.group_id, "member_id": contribution.member_id},
    )
    contribution.gateway = gateway.name
    contribution.gateway_reference = session.gateway_reference
    contribution.checkout_url = session.url
    contribution.save(update_fields=["gateway", "gateway_reference", "checkout_url"])
    return session.url


# --- Confirmation -------------------------------------------------------------

@transaction.atomic
def confirm_contribution(reference: str, *, paid_amount: Decimal | None = None, gateway_reference: str = "") -> ConfirmResult:
    """Mark a contribution paid exactly once and evaluate the group's funding threshold."""
    contribution = Contribution.objects.select_for_update().get(reference=reference)
    if contribution.status == ContributionStatus.PAID:
        return ConfirmResult(contribution, False)

    if paid_amount is not None and paid_amount < contribution.amount:
        contribution.status = ContributionStatus.FAILED
        contribution.failure_reason = "Gateway reported less than the expected amount"
        contribution.needs_review = True
        contribution.review_note = f"Expected {contribution.amount}, gateway reported {paid_amount}"
        contribution.save()
        log.error("Short payment on %s: expected %s got %s", reference, contribution.amount, paid_amount)
        return ConfirmResult(contribution, False)

    group = ContributionGroup.objects.select_for_update().get(pk=contribution.group_id)
    contribution.status = ContributionStatus.PAID
    contribution.paid_at = timezone.now()
    contribution.failure_reason = ""
    if gateway_reference:
        contribution.gateway_reference = gateway_reference
    notes = []
    if paid_amount is not None and paid_amount > contribution.amount:
        notes.append(f"Gateway reported {paid_amount}; credited {contribution.amount}")
    if not group.is_open_for_contributions:
        notes.append(f"Arrived after the group was {group.get_status_display().lower()}")
    membership = group.memberships.filter(user_id=contribution.member_id).first()
    already_paid = Contribution.objects.filter(group=group, member_id=contribution.member_id).total()
    if membership and already_paid + contribution.amount > membership.contribution_share:
        notes.append("Member has now paid more than their share")
    if notes:
        contribution.needs_review = True
        contribution.review_note = "; ".join(notes)[:250]
        log.warning("Contribution %s needs review: %s", reference, contribution.review_note)
    contribution.save()

    events.contribution_received(contribution)
    evaluate_funding(group.pk)
    return ConfirmResult(contribution, True)


@transaction.atomic
def fail_contribution(reference: str, reason: str = "Payment failed") -> Contribution:
    contribution = Contribution.objects.select_for_update().get(reference=reference)
    if contribution.status == ContributionStatus.PENDING:
        contribution.status = ContributionStatus.FAILED
        contribution.failure_reason = reason[:200]
        contribution.save(update_fields=["status", "failure_reason"])
    return contribution


def verify_and_confirm(contribution: Contribution) -> Contribution:
    """Ask the gateway directly (used on the customer's return trip so they don't wait for the webhook)."""
    if contribution.status != ContributionStatus.PENDING:
        return contribution
    try:
        result = get_gateway(contribution.gateway or None).verify_payment(contribution.reference)
    except GatewayError:
        log.exception("Could not verify %s", contribution.reference)
        return contribution
    if result.status == "success":
        return confirm_contribution(
            contribution.reference, paid_amount=result.amount, gateway_reference=result.gateway_reference
        ).contribution
    if result.status == "failed":
        return fail_contribution(contribution.reference)
    return contribution


# --- Funding threshold -----------------------------------------------------------

def evaluate_funding(group_id: int) -> bool:
    """Flip a group to FUNDED when confirmed contributions reach the target, and request its payout.

    Safe to call repeatedly: the status check under a row lock means the transition (and therefore
    the payout request and notifications) happens at most once.
    """
    from apps.payouts.services import request_payout

    with transaction.atomic():
        group = ContributionGroup.objects.select_for_update().get(pk=group_id)
        if group.status not in (GroupStatus.OPEN, GroupStatus.OVERDUE):
            return False
        if total_funded(group) < group.target_amount:
            return False
        group.status = GroupStatus.FUNDED
        group.funded_at = timezone.now()
        group.save(update_fields=["status", "funded_at", "updated_at"])
        events.group_funded(group)
        request_payout(group)
        return True


# --- Webhooks ---------------------------------------------------------------------

def process_webhook(provider: str, raw_body: bytes, payload: dict) -> str:
    """Record and act on a gateway event. Returns 'processed', 'duplicate' or 'ignored'."""
    from apps.payouts.services import apply_transfer_result

    gateway = get_gateway(provider)
    data = gateway.parse_webhook(payload)
    if data.kind == "other" or not data.event_id:
        return "ignored"

    try:
        with transaction.atomic():
            event, created = WebhookEvent.objects.get_or_create(
                provider=provider,
                event_id=data.event_id,
                defaults={"event_type": data.kind, "reference": data.reference, "payload": payload},
            )
    except IntegrityError:  # lost a create race with a concurrent identical delivery
        event, created = WebhookEvent.objects.get(provider=provider, event_id=data.event_id), False

    if not created:
        WebhookEvent.objects.filter(pk=event.pk).update(delivery_count=event.delivery_count + 1)
        if event.status in (WebhookEvent.Status.PROCESSED, WebhookEvent.Status.IGNORED):
            return "duplicate"

    try:
        outcome = "processed"
        if data.kind == "charge.success":
            confirm_contribution(data.reference, paid_amount=data.amount, gateway_reference=data.gateway_reference)
        elif data.kind == "transfer.success":
            apply_transfer_result(data.reference, "success", data.gateway_reference)
        elif data.kind == "transfer.failed":
            apply_transfer_result(data.reference, "failed", data.gateway_reference)
    except Contribution.DoesNotExist:
        # Not ours (e.g. another integration on the same account): acknowledge so it isn't retried forever.
        outcome = "ignored"
        log.warning("Webhook for unknown reference %s", data.reference)
    except Exception as exc:
        WebhookEvent.objects.filter(pk=event.pk).update(status=WebhookEvent.Status.FAILED, error=str(exc)[:1000])
        raise
    WebhookEvent.objects.filter(pk=event.pk).update(
        status=WebhookEvent.Status.PROCESSED if outcome == "processed" else WebhookEvent.Status.IGNORED,
        processed_at=timezone.now(),
        error="",
    )
    return outcome
