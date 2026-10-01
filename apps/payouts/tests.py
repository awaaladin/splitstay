from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.billpay.models import BillPayment
from apps.groups.models import GroupStatus
from apps.notifications.models import Notification
from apps.payouts.fees import quote_fee
from apps.payouts.models import Fee, PayoutStatus
from apps.payouts.services import get_payout_record, retry_payout
from apps.testing import make_group, pay


class FeeTests(TestCase):
    @override_settings(SERVICE_FEE_TYPE="flat", SERVICE_FEE_FLAT=Decimal("200"))
    def test_flat_fee(self):
        quote = quote_fee(Decimal("50000"))
        self.assertEqual((quote.fee_type, quote.amount, quote.net(Decimal("50000"))), ("flat", Decimal("200.00"), Decimal("49800.00")))

    @override_settings(SERVICE_FEE_TYPE="percent", SERVICE_FEE_PERCENT=Decimal("1.5"), SERVICE_FEE_MIN=0, SERVICE_FEE_MAX=0)
    def test_percentage_fee_rounds_to_kobo(self):
        self.assertEqual(quote_fee(Decimal("33333.33")).amount, Decimal("500.00"))

    @override_settings(SERVICE_FEE_TYPE="percent", SERVICE_FEE_PERCENT=Decimal("2"), SERVICE_FEE_MIN=Decimal("100"), SERVICE_FEE_MAX=Decimal("1000"))
    def test_percentage_fee_respects_floor_and_cap(self):
        self.assertEqual(quote_fee(Decimal("2000")).amount, Decimal("100.00"))
        self.assertEqual(quote_fee(Decimal("500000")).amount, Decimal("1000.00"))

    def test_fee_larger_than_pool_is_refused(self):
        with self.assertRaises(ValidationError):
            quote_fee(Decimal("100"))


class BillPaymentFlowTests(TestCase):
    def bill_group(self, meter="45012345678"):
        return make_group(
            target="30000", members=1, purpose="electricity", payout_type="bill_payment",
            bill_service_id="ikeja-electric", bill_customer_id=meter, bill_variation="prepaid",
            recipient_bank_code="", recipient_bank_name="", recipient_account_name="", recipient_account_number="",
        )

    def fund(self, group):
        with self.captureOnCommitCallbacks(execute=True):
            for m in group.memberships.all():
                pay(group, m.user)
        group.refresh_from_db()

    def test_funded_bill_group_pays_bill_with_token_and_fee_record(self):
        group = self.bill_group()
        self.fund(group)
        bill = BillPayment.objects.get(group=group)
        self.assertEqual(bill.status, PayoutStatus.COMPLETED)
        self.assertEqual((bill.gross_amount, bill.fee_amount, bill.net_amount),
                         (Decimal("30000.00"), Decimal("150.00"), Decimal("29850.00")))
        self.assertTrue(bill.token)
        self.assertEqual(Fee.objects.get(bill_payment=bill).amount, Decimal("150.00"))
        self.assertEqual(group.status, GroupStatus.PAID_OUT)

    def test_rejected_bill_fails_group_stays_funded_and_can_retry(self):
        group = self.bill_group(meter="45012349999")  # the mock provider rejects meters ending 9999
        self.fund(group)
        bill = BillPayment.objects.get(group=group)
        self.assertEqual(bill.status, PayoutStatus.FAILED)
        self.assertEqual(group.status, GroupStatus.FUNDED)
        self.assertEqual(Notification.objects.filter(kind="payout_failed", group=group).count(), 2)
        old_reference = bill.reference
        group.bill_customer_id = "45012345678"
        group.save()
        with self.captureOnCommitCallbacks(execute=True):
            retry_payout(group)
        bill.refresh_from_db()
        # the retry ran under a fresh reference, so the failed request id is never resent
        self.assertNotEqual(bill.reference, old_reference)
        self.assertEqual(Fee.objects.filter(bill_payment=bill).count(), 1)

    def test_provider_timeout_leaves_payment_processing_not_failed(self):
        from unittest import mock

        from apps.billpay.providers import BillProviderUnavailable
        from apps.billpay.providers.mock import MockBillProvider

        group = self.bill_group()
        with mock.patch.object(MockBillProvider, "pay", side_effect=BillProviderUnavailable("timeout")):
            self.fund(group)
        bill = BillPayment.objects.get(group=group)
        self.assertEqual(bill.status, PayoutStatus.PROCESSING)
        self.assertEqual(group.status, GroupStatus.FUNDED)
        self.assertIsNotNone(get_payout_record(group))
