from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from apps.groups.models import GroupStatus
from apps.notifications.models import Notification
from apps.payments.gateways.base import GatewayRejected
from apps.payouts.models import Payout, PayoutStatus
from apps.payouts.reasons import PLATFORM_DELAY, PLATFORM_FUNDS, friendly_failure_reason
from apps.testing import make_group, pay

STARTER = "You cannot initiate third party payouts as a starter business"


class FriendlyReasonTests(TestCase):
    def test_starter_business_refusal_is_reworded_for_members(self):
        self.assertEqual(friendly_failure_reason(STARTER), PLATFORM_DELAY)
        self.assertEqual(friendly_failure_reason("Your balance is not enough to fulfill this request"), PLATFORM_FUNDS)
        self.assertEqual(friendly_failure_reason("Account number is invalid"), "Account number is invalid")


class RefusedTransferTests(TestCase):
    def setUp(self):
        self.group = make_group(target="60000", members=1)  # two people
        gateway = mock.MagicMock()
        gateway.name = "paystack"
        gateway.initiate_transfer.side_effect = GatewayRejected(STARTER)
        with mock.patch("apps.payouts.services.get_gateway", return_value=gateway), self.captureOnCommitCallbacks(execute=True):
            for m in self.group.memberships.all():
                pay(self.group, m.user)
        self.group.refresh_from_db()
        self.payout = Payout.objects.get()

    def test_money_is_kept_and_the_reason_is_member_friendly(self):
        self.assertEqual(self.payout.status, PayoutStatus.FAILED)
        self.assertEqual(self.payout.failure_reason, PLATFORM_DELAY)
        self.assertEqual(self.group.status, GroupStatus.FUNDED)

    def test_members_are_told_nothing_is_needed_from_them(self):
        note = Notification.objects.filter(kind="payout_failed").first()
        self.assertIn("payout delayed", note.title)
        self.assertIn("No action is needed from you", note.body)
        self.assertNotIn("starter business", note.body.lower())

    def test_manual_command_shows_the_details_and_changes_nothing_without_confirm(self):
        out = StringIO()
        call_command("manual_payout", str(self.group.pk), stdout=out)
        text = out.getvalue()
        self.assertIn("N59,850.00", text)  # the test settings still deduct the old flat N150 at payout
        self.assertIn("0123456789", text)  # the operator needs the full account number to send the money
        self.assertIn("Nothing was changed", text)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.FAILED)

    def test_confirm_requires_a_bank_reference(self):
        with self.assertRaises(CommandError):
            call_command("manual_payout", str(self.group.pk), "--confirm", stdout=StringIO())
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.FAILED)

    def test_confirming_closes_the_group_notifies_members_and_shows_the_reference_on_the_receipt(self):
        call_command("manual_payout", str(self.group.pk), "--confirm", "--reference", "GTB-123456", stdout=StringIO())
        self.payout.refresh_from_db()
        self.group.refresh_from_db()
        self.assertEqual((self.payout.status, self.payout.gateway, self.payout.gateway_reference),
                         (PayoutStatus.COMPLETED, "manual", "GTB-123456"))
        self.assertIsNotNone(self.payout.completed_at)
        self.assertEqual(self.group.status, GroupStatus.PAID_OUT)
        self.assertTrue(Notification.objects.filter(kind="payout_done", group=self.group).exists())
        self.client.login(username=self.group.admin.email, password="pass12345!")
        html = self.client.get(reverse("web:group_receipt", args=[self.group.pk])).content.decode()
        self.assertIn("GTB-123456", html)
        self.assertIn("₦59,850.00", html)

    def test_a_completed_payout_cannot_be_settled_twice(self):
        call_command("manual_payout", str(self.group.pk), "--confirm", "--reference", "REF-1", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("manual_payout", str(self.group.pk), "--confirm", "--reference", "REF-2", stdout=StringIO())
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.gateway_reference, "REF-1")

    def test_a_payout_paystack_may_still_be_processing_is_refused(self):
        Payout.objects.filter(pk=self.payout.pk).update(status=PayoutStatus.PROCESSING)
        with self.assertRaises(CommandError):
            call_command("manual_payout", str(self.group.pk), "--confirm", "--reference", "REF-3", stdout=StringIO())

    def test_unknown_group_and_bill_groups_are_refused(self):
        with self.assertRaises(CommandError):
            call_command("manual_payout", "99999", stdout=StringIO())
