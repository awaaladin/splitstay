import csv
import json
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.contributions.models import Contribution
from apps.contributions.services import initiate_contribution
from apps.payments import services
from apps.payments.gateways.mock import MockGateway
from apps.payments.models import WebhookEvent
from apps.payments.naming import APP_CODE, is_ours, make_reference, make_transfer_reference, paystack_metadata
from apps.payments.tests import charge_success, signed_post
from apps.payouts.models import Payout
from apps.testing import make_group, make_user, pay


class ReferenceNamingTests(TestCase):
    def test_collections_carry_the_app_prefix_and_fit_the_columns(self):
        group = make_group(target="90000", members=1)
        contribution = initiate_contribution(group, group.admin)
        self.assertTrue(contribution.reference.startswith("SPLITPAY-CONTRIB-"))
        self.assertLessEqual(len(contribution.reference), 40)  # Contribution.reference max_length
        self.assertRegex(contribution.reference, r"^SPLITPAY-CONTRIB-\d{8}-[0-9A-F]{12}$")

    def test_transfers_are_lowercase_and_carry_the_app_prefix(self):
        reference = make_transfer_reference("PAYOUT")
        self.assertTrue(reference.startswith("splitpay-payout-"))
        self.assertEqual(reference, reference.lower())
        self.assertTrue(16 <= len(reference) <= 50)  # Paystack's transfer reference limits

    def test_references_are_unique(self):
        self.assertEqual(len({make_reference("CONTRIB") for _ in range(500)}), 500)

    def test_metadata_labels_the_transaction_for_the_dashboard(self):
        meta = paystack_metadata("CONTRIB", "Contribution to Flat 4B", group_id=3)
        self.assertEqual((meta["app"], meta["app_name"], meta["group_id"]), (APP_CODE, "SplitPay", 3))
        self.assertIn({"display_name": "App", "variable_name": "app", "value": "SplitPay"}, meta["custom_fields"])

    def test_checkout_sends_the_metadata_to_the_gateway(self):
        group = make_group(target="90000", members=1)
        contribution = initiate_contribution(group, group.admin)
        with mock.patch.object(MockGateway, "initialize_payment", wraps=MockGateway().initialize_payment) as spy:
            services.start_checkout(contribution)
        self.assertEqual(spy.call_args.kwargs["reference"], contribution.reference)
        self.assertEqual(spy.call_args.kwargs["metadata"]["app"], "SPLITPAY")

    def test_payout_reference_comes_from_the_naming_scheme(self):
        group = make_group(target="60000", members=1)
        with self.captureOnCommitCallbacks(execute=True):
            for m in group.memberships.all():
                pay(group, m.user)
        self.assertTrue(Payout.objects.get().reference.startswith("splitpay-payout-"))


class OwnershipTests(TestCase):
    def test_is_ours(self):
        self.assertTrue(is_ours("SPLITPAY-CONTRIB-20261023-ABC"))
        self.assertTrue(is_ours("splitpay-payout-20261023-abc"))
        self.assertTrue(is_ours("SPLITPAY-CONTRIB-1", {"app": "splitpay"}))
        self.assertFalse(is_ours("CHOROPIA-ORDER-20261023-ABC"))
        self.assertFalse(is_ours("SPLITPAY-CONTRIB-1", {"app": "MIRROR"}))  # metadata contradicts the prefix
        self.assertFalse(is_ours(""))
        self.assertFalse(is_ours("ORDER-SPLITPAY-1"))  # must START with our code

    def setUp(self):
        self.client = APIClient()
        self.group = make_group(target="90000", members=2)
        self.contribution = initiate_contribution(self.group, self.group.admin)

    def test_events_for_other_apps_are_acknowledged_but_never_stored_or_applied(self):
        for ref in ("CHOROPIA-ORDER-20261023-4F9A2C7B1E0D", "MIRROR-PRO-20261023-9C1E0D4F9A2C", "order-12-abc"):
            res = signed_post(self.client, {"event": "charge.success", "data": {"id": 5, "reference": ref, "amount": 100000}})
            self.assertEqual((res.status_code, res.data["status"]), (200, "ignored"), ref)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_our_reference_with_another_apps_metadata_is_ignored(self):
        payload = charge_success(self.contribution)
        payload["data"]["metadata"] = {"app": "NUTRISCAN"}
        self.assertEqual(signed_post(self.client, payload).data["status"], "ignored")
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, "pending")

    def test_our_own_event_with_our_metadata_is_processed(self):
        payload = charge_success(self.contribution)
        payload["data"]["metadata"] = paystack_metadata("CONTRIB", "x")
        self.assertEqual(signed_post(self.client, payload).data["status"], "processed")


class GatewayFeeAndReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.group = make_group(target="60000", members=1)  # two members, 30,000 each

    def test_paystacks_real_fee_is_recorded_from_the_webhook(self):
        contribution = initiate_contribution(self.group, self.group.admin)
        payload = charge_success(contribution)
        payload["data"]["fees"] = 45000  # kobo => N450.00
        signed_post(self.client, payload)
        contribution.refresh_from_db()
        self.assertEqual(contribution.gateway_fee, Decimal("450.00"))

    def test_a_late_duplicate_can_still_fill_in_a_missing_fee(self):
        contribution = initiate_contribution(self.group, self.group.admin)
        services.confirm_contribution(contribution.reference, paid_amount=contribution.amount)
        services.confirm_contribution(contribution.reference, paid_amount=contribution.amount, gateway_fee=Decimal("450"))
        contribution.refresh_from_db()
        self.assertEqual(contribution.gateway_fee, Decimal("450.00"))

    def test_profit_and_loss_report(self):
        with self.captureOnCommitCallbacks(execute=True):
            for m in self.group.memberships.all():
                services.confirm_contribution(
                    initiate_contribution(self.group, m.user).reference, paid_amount=Decimal("30000"), gateway_fee=Decimal("450"))
        out = StringIO()
        target = Path(tempfile.mkdtemp()) / "report.csv"
        call_command("splitpay_report", "--csv", str(target), stdout=out)
        text = out.getvalue()
        self.assertIn("N60,000.00", text)  # collected
        self.assertIn("N150.00", text)  # revenue: the service fee
        self.assertIn("N900.00", text)  # Paystack collection costs: 2 x 450
        self.assertIn("LOSS", text)  # 150 fee earned vs 900 + 25 transfer: this pricing loses money
        rows = list(csv.DictReader(target.open(encoding="utf-8")))
        self.assertEqual(sorted(r["type"] for r in rows), ["collection", "collection", "transfer"])
        self.assertTrue(all(r["reference"].upper().startswith("SPLITPAY-") for r in rows))

    def test_report_warns_about_missing_fees_and_handles_an_empty_period(self):
        pay(self.group, self.group.admin)  # no gateway fee recorded
        out = StringIO()
        call_command("splitpay_report", stdout=out)
        self.assertIn("no recorded Paystack fee", out.getvalue())
        out = StringIO()
        call_command("splitpay_report", "--from", "2020-01-01", "--to", "2020-01-31", stdout=out)
        self.assertIn("PROFIT", out.getvalue())


class ElectricityGuardTests(TestCase):
    def payload(self):
        return {
            "name": "Light", "purpose": "electricity", "target_amount": "30000",
            "due_date": (date.today() + timedelta(days=5)).isoformat(), "payout_type": "bill_payment",
            "bill_service_id": "ikeja-electric", "bill_customer_id": "45012345678", "bill_variation": "prepaid",
        }

    def test_api_refuses_new_bill_groups_when_bills_cannot_really_be_paid(self):
        client = APIClient()
        client.force_authenticate(make_user("Admin"))
        with override_settings(BILL_PAYMENTS_ENABLED=False):
            res = client.post("/api/v1/groups/", self.payload(), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("payout_type", res.data)
        self.assertEqual(client.post("/api/v1/groups/", self.payload(), format="json").status_code, 201)

    def test_web_form_refuses_and_page_says_coming_soon(self):
        user = make_user("Web", password="pass12345!")
        self.client.login(username=user.email, password="pass12345!")
        with override_settings(BILL_PAYMENTS_ENABLED=False):
            self.assertContains(self.client.get("/groups/new/"), "Coming soon")

    def test_enabled_logic_never_pairs_a_mock_provider_with_a_real_gateway(self):
        import importlib

        from config.settings import base

        def enabled(**env):
            with mock.patch.dict("os.environ", env, clear=False):
                return importlib.reload(base).BILL_PAYMENTS_ENABLED

        try:
            self.assertTrue(enabled(PAYMENT_GATEWAY="mock", BILL_PROVIDER="mock"))
            self.assertFalse(enabled(PAYMENT_GATEWAY="paystack", BILL_PROVIDER="mock"))
            self.assertFalse(enabled(PAYMENT_GATEWAY="paystack", BILL_PROVIDER="vtpass", VTPASS_API_KEY="", VTPASS_SECRET_KEY=""))
            self.assertTrue(enabled(PAYMENT_GATEWAY="paystack", BILL_PROVIDER="vtpass", VTPASS_API_KEY="k", VTPASS_SECRET_KEY="s"))
        finally:
            importlib.reload(base)
