"""Payout orchestration for both bank transfers and bill payments.

request_payout() is the single entry point (auto trigger on funding, or the admin's manual trigger).
It is idempotent: a group has at most one Payout / BillPayment (OneToOne), created under a row lock.
Actual money movement happens later in a Celery task, so no network call runs inside a DB transaction.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.contributions.selectors import total_funded
from apps.groups.models import ContributionGroup, GroupStatus, PayoutType
from apps.notifications import events
from apps.payments.gateways import GatewayRejected, GatewayUnavailable, get_gateway

from .fees import quote_fee
from .models import Fee, Payout, PayoutStatus, new_payout_reference

log = logging.getLogger(__name__)


def get_payout_record(group: ContributionGroup):
    """The group's Payout or BillPayment, or None."""
    # Reverse one-to-one accessors raise (an AttributeError subclass) when absent; getattr's default handles it.
    return getattr(group, "bill_payment" if group.payout_type == PayoutType.BILL_PAYMENT else "payout", None)


def _schedule(kind: str, pk: int) -> None:
    from .tasks import execute_payout

    transaction.on_commit(lambda: execute_payout.delay(kind, pk))


@transaction.atomic
def request_payout(group: ContributionGroup, *, triggered_by=None, partial: bool = False):
    """Create the payout record for a funded group (or a partial one if the group allows it)."""
    from apps.billpay.models import BillPayment

    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    existing = get_payout_record(group)
    if existing is not None:
        return existing  # idempotent: never a second payout for the same group

    total = total_funded(group)
    if group.status == GroupStatus.FUNDED:
        pass
    elif group.status in (GroupStatus.OPEN, GroupStatus.OVERDUE) and partial:
        if not group.allow_partial_payout:
            raise ValidationError("This group does not allow payout before the target is reached.")
        if total <= 0:
            raise ValidationError("Nothing has been contributed yet.")
        group.status = GroupStatus.FUNDED
        group.funded_at = timezone.now()
        group.save(update_fields=["status", "funded_at", "updated_at"])
    else:
        raise ValidationError(f"A {group.get_status_display().lower()} group cannot be paid out.")

    quote = quote_fee(total)
    is_partial = total < group.target_amount

    if group.payout_type == PayoutType.BILL_PAYMENT:
        record = BillPayment.objects.create(
            group=group, gross_amount=total, fee_amount=quote.amount, net_amount=total - quote.amount,
            service_id=group.bill_service_id, customer_id=group.bill_customer_id,
            variation=group.bill_variation, is_partial=is_partial, triggered_by=triggered_by,
        )
        Fee.objects.create(bill_payment=record, fee_type=quote.fee_type, rate=quote.rate, amount=quote.amount)
        _schedule("bill", record.pk)
    else:
        record = Payout.objects.create(
            group=group, gross_amount=total, fee_amount=quote.amount, net_amount=total - quote.amount,
            recipient_bank_code=group.recipient_bank_code, recipient_bank_name=group.recipient_bank_name,
            recipient_account_name=group.recipient_account_name,
            recipient_account_number=group.recipient_account_number,
            recipient_account_last4=(group.recipient_account_number or "")[-4:],
            is_partial=is_partial, triggered_by=triggered_by,
        )
        Fee.objects.create(payout=record, fee_type=quote.fee_type, rate=quote.rate, amount=quote.amount)
        _schedule("transfer", record.pk)
    return record


@transaction.atomic
def retry_payout(group: ContributionGroup):
    """Re-attempt a FAILED payout under a fresh reference (the failed attempt is never re-sent)."""
    group = ContributionGroup.objects.select_for_update().get(pk=group.pk)
    record = get_payout_record(group)
    if record is None or record.status != PayoutStatus.FAILED:
        raise ValidationError("There is no failed payout to retry.")
    if group.payout_type == PayoutType.BILL_PAYMENT:
        from apps.billpay.models import new_bill_reference

        record.reference = new_bill_reference()
        kind = "bill"
    else:
        record.reference = new_payout_reference()
        kind = "transfer"
    record.status = PayoutStatus.PENDING
    record.failure_reason = ""
    record.save()
    _schedule(kind, record.pk)
    return record


# --- Execution (called from Celery) -------------------------------------------------

def execute_transfer(payout_id: int) -> None:
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout_id)
        if payout.status != PayoutStatus.PENDING:
            return  # already picked up: duplicate task delivery is harmless
        payout.status = PayoutStatus.PROCESSING
        payout.attempts += 1
        payout.save(update_fields=["status", "attempts", "updated_at"])

    gateway = get_gateway()
    try:
        result = gateway.initiate_transfer(
            reference=payout.reference, amount=payout.net_amount,
            account_number=payout.recipient_account_number, bank_code=payout.recipient_bank_code,
            account_name=payout.recipient_account_name, narration=f"SplitStay: {payout.group.name}",
        )
    except GatewayRejected as exc:
        _finish_transfer(payout.pk, PayoutStatus.FAILED, reason=str(exc))
        return
    except GatewayUnavailable as exc:
        # Outcome unknown: leave PROCESSING. reconcile_pending() will ask the gateway by reference.
        log.error("Transfer %s outcome unknown: %s", payout.reference, exc)
        Payout.objects.filter(pk=payout.pk).update(gateway=gateway.name)
        return

    Payout.objects.filter(pk=payout.pk).update(gateway=gateway.name, gateway_reference=result.gateway_reference)
    if result.status == "success":
        _finish_transfer(payout.pk, PayoutStatus.COMPLETED)
    elif result.status == "failed":
        _finish_transfer(payout.pk, PayoutStatus.FAILED, reason=result.message or "Transfer failed")
    # "pending": the transfer.success / transfer.failed webhook (or reconciliation) settles it.


def _finish_transfer(payout_id: int, status: str, reason: str = "") -> None:
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout_id)
        if payout.status == PayoutStatus.COMPLETED:
            return  # terminal and immutable
        group = ContributionGroup.objects.select_for_update().get(pk=payout.group_id)
        payout.status = status
        if status == PayoutStatus.COMPLETED:
            payout.completed_at = timezone.now()
            payout.failure_reason = ""
            group.status = GroupStatus.PAID_OUT
            group.save(update_fields=["status", "updated_at"])
            payout.save()
            events.payout_completed(group, payout)
        else:
            payout.failure_reason = reason[:250]
            payout.save()
            events.payout_failed(group, payout)


def apply_transfer_result(reference: str, status: str, gateway_reference: str = "") -> None:
    """Webhook entry point. Idempotent: repeated events change nothing once terminal."""
    payout = Payout.objects.filter(reference=reference).first()
    if payout is None:
        log.warning("Transfer webhook for unknown reference %s", reference)
        return
    if status == "success":
        if gateway_reference:
            Payout.objects.filter(pk=payout.pk).update(gateway_reference=gateway_reference)
        _finish_transfer(payout.pk, PayoutStatus.COMPLETED)
    elif status == "failed" and payout.status in (PayoutStatus.PROCESSING, PayoutStatus.PENDING):
        _finish_transfer(payout.pk, PayoutStatus.FAILED, reason="Transfer failed or was reversed")


def reconcile_processing(older_than_minutes: int = 2) -> int:
    """Settle payouts stuck in PROCESSING by asking the gateway directly. Returns how many changed."""
    from datetime import timedelta

    from apps.billpay.services import reconcile_bill_payment

    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    changed = 0
    for payout in Payout.objects.filter(status=PayoutStatus.PROCESSING, updated_at__lt=cutoff):
        try:
            result = get_gateway(payout.gateway or None).verify_transfer(payout.reference)
        except (GatewayRejected, GatewayUnavailable):
            log.warning("Could not reconcile %s", payout.reference)
            continue
        if result.status == "success":
            _finish_transfer(payout.pk, PayoutStatus.COMPLETED)
            changed += 1
        elif result.status == "failed":
            _finish_transfer(payout.pk, PayoutStatus.FAILED, reason="Transfer failed at gateway")
            changed += 1
    from apps.billpay.models import BillPayment

    for bill in BillPayment.objects.filter(status=PayoutStatus.PROCESSING, updated_at__lt=cutoff):
        changed += int(reconcile_bill_payment(bill.pk))
    return changed
