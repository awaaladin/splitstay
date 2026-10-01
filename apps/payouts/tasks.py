from celery import shared_task

from . import services


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def execute_payout(self, kind: str, pk: int) -> None:
    """kind is 'transfer' (bank payout) or 'bill' (bill payment)."""
    if kind == "bill":
        from apps.billpay.services import execute_bill_payment

        execute_bill_payment(pk)
    else:
        services.execute_transfer(pk)


@shared_task
def reconcile_pending() -> int:
    return services.reconcile_processing()
