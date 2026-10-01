import logging

from django.db import transaction
from django.utils import timezone

from apps.groups.models import ContributionGroup, GroupStatus
from apps.notifications import events
from apps.payouts.models import PayoutStatus

from .models import BillPayment
from .providers import BillProviderUnavailable, BillResult, get_provider

log = logging.getLogger(__name__)


def validate_meter(service_id: str, customer_id: str, variation: str):
    return get_provider().validate_customer(service_id=service_id, customer_id=customer_id, variation=variation)


def execute_bill_payment(pk: int) -> None:
    with transaction.atomic():
        bill = BillPayment.objects.select_for_update().select_related("group__admin__profile").get(pk=pk)
        if bill.status != PayoutStatus.PENDING:
            return  # duplicate task delivery
        bill.status = PayoutStatus.PROCESSING
        bill.attempts += 1
        bill.save(update_fields=["status", "attempts", "updated_at"])

    provider = get_provider()
    phone = getattr(bill.group.admin.profile, "phone_number", None) or "08011111111"
    try:
        result = provider.pay(
            request_id=bill.reference, service_id=bill.service_id, customer_id=bill.customer_id,
            amount=bill.net_amount, variation=bill.variation, phone=phone,
        )
    except BillProviderUnavailable as exc:
        # The purchase may have gone through. Stay PROCESSING; reconcile via requery, never re-pay blindly.
        log.error("Bill %s outcome unknown: %s", bill.reference, exc)
        BillPayment.objects.filter(pk=bill.pk).update(provider=provider.name)
        return
    BillPayment.objects.filter(pk=bill.pk).update(provider=provider.name)
    apply_result(bill.pk, result)


def apply_result(pk: int, result: BillResult) -> None:
    with transaction.atomic():
        bill = BillPayment.objects.select_for_update().get(pk=pk)
        if bill.status == PayoutStatus.COMPLETED:
            return
        if result.provider_reference:
            bill.provider_reference = result.provider_reference
        if result.status == "success":
            group = ContributionGroup.objects.select_for_update().get(pk=bill.group_id)
            bill.status = PayoutStatus.COMPLETED
            bill.completed_at = timezone.now()
            bill.token = result.token
            bill.units = result.units
            bill.customer_name = result.customer_name or bill.customer_name
            bill.failure_reason = ""
            bill.save()
            group.status = GroupStatus.PAID_OUT
            group.save(update_fields=["status", "updated_at"])
            events.payout_completed(group, bill)
        elif result.status == "failed":
            group = bill.group
            bill.status = PayoutStatus.FAILED
            bill.failure_reason = (result.message or "Biller rejected the payment")[:250]
            bill.save()
            events.payout_failed(group, bill)
        else:
            bill.save(update_fields=["provider_reference", "updated_at"])  # still pending at the biller


def reconcile_bill_payment(pk: int) -> bool:
    """Ask the provider what happened to a PROCESSING bill. True if it reached a final state."""
    bill = BillPayment.objects.get(pk=pk)
    try:
        result = get_provider(bill.provider or None).requery(bill.reference)
    except BillProviderUnavailable:
        return False
    if result.status == "pending":
        return False
    apply_result(pk, result)
    return True
