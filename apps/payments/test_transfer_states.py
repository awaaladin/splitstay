from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.groups.models import GroupStatus
from apps.payments.gateways.paystack import PaystackGateway
from apps.payouts.models import Payout, PayoutStatus
from apps.testing import make_group, pay


def fake_request(responses):
    """A stand-in for PaystackGateway._request that returns canned `data` per path."""
    def request(self, method, path, **kwargs):
        return responses[path]
    return request


class TransferStateTests(TestCase):
    def transfer(self, status):
        gateway = PaystackGateway(secret_key="sk_test_x")
        responses = {"/transferrecipient": {"recipient_code": "RCP_1"}, "/transfer": {"status": status, "transfer_code": "TRF_1"}}
        with mock.patch.object(PaystackGateway, "_request", fake_request(responses)):
            return gateway.initiate_transfer(reference="splitpay-payout-20261024-aaaaaaaaaaaaaaaa", amount=Decimal("1000"),
                                             account_number="0123456789", bank_code="058", account_name="Landlord", narration="SplitPay: x")

    def test_otp_is_a_clear_failure_not_an_endless_pending(self):
        result = self.transfer("otp")
        self.assertEqual(result.status, "failed")
        self.assertIn("OTP", result.message)

    def test_normal_statuses_still_map(self):
        self.assertEqual(self.transfer("success").status, "success")
        self.assertEqual(self.transfer("pending").status, "pending")
        self.assertEqual(self.transfer("reversed").status, "failed")

    def test_an_otp_payout_is_marked_failed_and_the_money_stays_in_the_group(self):
        group = make_group(target="60000", members=1)
        from apps.payments.gateways.base import TransferResult

        with mock.patch("apps.payouts.services.get_gateway") as get_gateway, self.captureOnCommitCallbacks(execute=True):
            get_gateway.return_value.name = "paystack"
            get_gateway.return_value.initiate_transfer.return_value = TransferResult("failed", "TRF_1", "Paystack requires an OTP")
            for m in group.memberships.all():
                pay(group, m.user)
        payout = Payout.objects.get()
        group.refresh_from_db()
        self.assertEqual(payout.status, PayoutStatus.FAILED)
        self.assertIn("OTP", payout.failure_reason)
        self.assertEqual(group.status, GroupStatus.FUNDED)  # not paid out; the admin can retry once fixed
