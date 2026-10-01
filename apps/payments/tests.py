import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.contributions.models import Contribution, ContributionStatus
from apps.contributions.selectors import total_funded
from apps.contributions.services import initiate_contribution
from apps.groups.models import GroupStatus
from apps.notifications.models import Notification
from apps.payments import services
from apps.payments.models import WebhookEvent
from apps.payouts.models import Fee, Payout, PayoutStatus
from apps.testing import make_group, pay

WEBHOOK_URL = "/api/v1/payments/webhooks/paystack/"
SECRET = "sk_test_unit"


def signed_post(client, payload: dict, secret=SECRET):
    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    return client.post(WEBHOOK_URL, data=body, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=sig)


def charge_success(contribution, *, event_id=987001, amount=None):
    kobo = int((amount or contribution.amount) * 100)
    return {"event": "charge.success", "data": {"id": event_id, "reference": contribution.reference, "amount": kobo}}


class FundingThresholdTests(TestCase):
    def setUp(self):
        self.group = make_group(target="90000", members=2)
        self.members = [m.user for m in self.group.memberships.order_by("id")]

    def test_group_stays_open_below_target(self):
        pay(self.group, self.members[0])
        pay(self.group, self.members[1])
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.OPEN)
        self.assertFalse(Payout.objects.exists())

    def test_reaching_target_funds_group_and_creates_one_payout_with_fee(self):
        with self.captureOnCommitCallbacks(execute=True):
            for user in self.members:
                pay(self.group, user)
        self.group.refresh_from_db()
        # mock gateway completes the transfer synchronously via the eager Celery task
        self.assertEqual(self.group.status, GroupStatus.PAID_OUT)
        self.assertIsNotNone(self.group.funded_at)
        payout = Payout.objects.get()
        self.assertEqual(payout.gross_amount, Decimal("90000.00"))
        self.assertEqual(payout.fee_amount, Decimal("150.00"))
        self.assertEqual(payout.net_amount, Decimal("89850.00"))
        self.assertEqual(payout.status, PayoutStatus.COMPLETED)
        fee = Fee.objects.get(payout=payout)
        self.assertEqual((fee.fee_type, fee.amount), ("flat", Decimal("150.00")))

    def test_evaluate_funding_is_idempotent(self):
        with self.captureOnCommitCallbacks(execute=True):
            for user in self.members:
                pay(self.group, user)
            self.assertFalse(services.evaluate_funding(self.group.pk))
            self.assertFalse(services.evaluate_funding(self.group.pk))
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(kind="funded").count(), 3)  # once per member

    def test_overdue_group_can_still_be_funded(self):
        self.group.status = GroupStatus.OVERDUE
        self.group.save()
        with self.captureOnCommitCallbacks(execute=True):
            for user in self.members:
                pay(self.group, user)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.PAID_OUT)

    def test_manual_partial_payout_only_when_group_allows(self):
        from django.core.exceptions import ValidationError

        from apps.payouts.services import request_payout

        pay(self.group, self.members[0])
        with self.assertRaises(ValidationError):
            request_payout(self.group, triggered_by=self.group.admin, partial=True)
        self.group.allow_partial_payout = True
        self.group.save()
        with self.captureOnCommitCallbacks(execute=True):
            payout = request_payout(self.group, triggered_by=self.group.admin, partial=True)
        payout.refresh_from_db()
        self.assertTrue(payout.is_partial)
        self.assertEqual(payout.gross_amount, Decimal("30000.00"))
        self.assertEqual(payout.net_amount, Decimal("29850.00"))

    def test_second_payout_request_returns_same_record(self):
        from apps.payouts.services import request_payout

        with self.captureOnCommitCallbacks(execute=True):
            for user in self.members:
                pay(self.group, user)
        self.group.refresh_from_db()
        again = request_payout(self.group)
        self.assertEqual(again.pk, Payout.objects.get().pk)

    def test_contribution_after_close_is_flagged_not_lost(self):
        contribution = initiate_contribution(self.group, self.members[0])
        self.group.status = GroupStatus.CANCELLED
        self.group.save()
        services.confirm_contribution(contribution.reference, paid_amount=contribution.amount)
        contribution.refresh_from_db()
        self.assertTrue(contribution.needs_review)
        self.assertEqual(contribution.status, ContributionStatus.PAID)


class WebhookIdempotencyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.group = make_group(target="90000", members=2)
        self.members = [m.user for m in self.group.memberships.order_by("id")]
        self.contribution = initiate_contribution(self.group, self.members[1])

    def test_duplicate_webhook_counts_contribution_once(self):
        payload = charge_success(self.contribution)
        first = signed_post(self.client, payload)
        second = signed_post(self.client, payload)
        third = signed_post(self.client, payload)
        self.assertEqual([first.status_code, second.status_code, third.status_code], [200, 200, 200])
        self.assertEqual(first.data["status"], "processed")
        self.assertEqual(second.data["status"], "duplicate")
        self.assertEqual(total_funded(self.group), Decimal("30000.00"))
        self.assertEqual(Contribution.objects.filter(status="paid").count(), 1)
        event = WebhookEvent.objects.get()
        self.assertEqual(event.delivery_count, 3)
        self.assertEqual(event.status, WebhookEvent.Status.PROCESSED)
        # one confirmation notification per audience member, not per delivery
        self.assertEqual(Notification.objects.filter(kind="contribution").count(), 3)

    def test_duplicate_final_webhook_never_creates_second_payout(self):
        with self.captureOnCommitCallbacks(execute=True):
            pay(self.group, self.members[0])
            pay(self.group, self.members[2])
            payload = charge_success(self.contribution, event_id=555)
            for _ in range(3):
                signed_post(self.client, payload)
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(Fee.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(kind="funded").count(), 3)
        self.assertEqual(Notification.objects.filter(kind="payout_done").count(), 3)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.PAID_OUT)

    def test_redelivery_after_a_failed_first_attempt_is_still_safe(self):
        """If the first attempt crashed after recording the event, the retry reprocesses without double counting."""
        payload = charge_success(self.contribution)
        WebhookEvent.objects.create(
            provider="paystack", event_id="charge.success:987001", event_type="charge.success",
            reference=self.contribution.reference, payload=payload, status=WebhookEvent.Status.FAILED,
        )
        for _ in range(2):
            self.assertEqual(signed_post(self.client, payload).status_code, 200)
        self.assertEqual(total_funded(self.group), Decimal("30000.00"))
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_confirm_contribution_directly_is_idempotent(self):
        first = services.confirm_contribution(self.contribution.reference, paid_amount=Decimal("30000"))
        second = services.confirm_contribution(self.contribution.reference, paid_amount=Decimal("30000"))
        self.assertTrue(first.newly_confirmed)
        self.assertFalse(second.newly_confirmed)
        self.assertEqual(total_funded(self.group), Decimal("30000.00"))

    def test_invalid_signature_is_rejected_and_changes_nothing(self):
        res = signed_post(self.client, charge_success(self.contribution), secret="wrong-secret")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(total_funded(self.group), Decimal("0.00"))
        self.assertFalse(WebhookEvent.objects.exists())

    def test_short_payment_is_not_credited(self):
        res = signed_post(self.client, charge_success(self.contribution, amount=Decimal("100")))
        self.assertEqual(res.status_code, 200)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.FAILED)
        self.assertTrue(self.contribution.needs_review)
        self.assertEqual(total_funded(self.group), Decimal("0.00"))

    def test_unknown_reference_is_acknowledged_not_retried_forever(self):
        payload = {"event": "charge.success", "data": {"id": 42, "reference": "NOT-OURS", "amount": 1000}}
        res = signed_post(self.client, payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "ignored")

    def test_unhandled_event_types_are_ignored(self):
        res = signed_post(self.client, {"event": "customeridentification.success", "data": {"id": 1}})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "ignored")

    def test_transfer_webhooks_are_idempotent(self):
        group = make_group(target="60000", members=1)
        members = [m.user for m in group.memberships.order_by("id")]
        with override_settings(PAYMENT_GATEWAY="paystack"), self.captureOnCommitCallbacks(execute=False):
            for u in members:
                pay(group, u)
        payout = Payout.objects.get(group=group)
        payout.status = PayoutStatus.PROCESSING
        payout.save()
        payload = {"event": "transfer.success", "data": {"id": 9, "reference": payout.reference, "transfer_code": "TRF_1"}}
        for _ in range(3):
            self.assertEqual(signed_post(self.client, payload).status_code, 200)
        payout.refresh_from_db()
        group.refresh_from_db()
        self.assertEqual(payout.status, PayoutStatus.COMPLETED)
        self.assertEqual(group.status, GroupStatus.PAID_OUT)
        self.assertEqual(Notification.objects.filter(kind="payout_done", group=group).count(), 2)
