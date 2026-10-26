"""The 5% service fee is ADDED to each member's payment; the pot and the recipient are never reduced."""
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.contributions.models import Contribution, ContributionStatus
from apps.contributions.selectors import total_funded
from apps.contributions.services import initiate_contribution
from apps.groups.models import GroupStatus
from apps.ledger import services as ledger
from apps.payments import services
from apps.payments.gateways.mock import MockGateway
from apps.payouts.fees import fee_for_payment, quote_fee
from apps.payouts.models import Fee, Payout
from apps.testing import make_group, pay

ON_TOP = dict(SERVICE_FEE_MODE="on_top", SERVICE_FEE_TYPE="percent", SERVICE_FEE_PERCENT=Decimal("5"),
              SERVICE_FEE_MIN=Decimal("0"), SERVICE_FEE_MAX=Decimal("0"))


@override_settings(**ON_TOP)
class FeePolicyTests(TestCase):
    def test_five_percent_of_each_payment(self):
        for share, fee in (("2000", "100.00"), ("5000", "250.00"), ("10000", "500.00"), ("37500", "1875.00"), ("150000", "7500.00")):
            self.assertEqual(fee_for_payment(Decimal(share)).amount, Decimal(fee), share)

    def test_rounds_to_the_kobo(self):
        self.assertEqual(fee_for_payment(Decimal("133333.34")).amount, Decimal("6666.67"))

    def test_minimum_and_maximum_apply_per_payment(self):
        with override_settings(SERVICE_FEE_MIN=Decimal("150"), SERVICE_FEE_MAX=Decimal("5000")):
            self.assertEqual(fee_for_payment(Decimal("1000")).amount, Decimal("150.00"))
            self.assertEqual(fee_for_payment(Decimal("150000")).amount, Decimal("5000.00"))

    def test_payouts_deduct_nothing_in_on_top_mode(self):
        self.assertEqual(quote_fee(Decimal("600000")).amount, Decimal("0.00"))

    def test_deduct_mode_still_works_and_adds_nothing_on_top(self):
        with override_settings(SERVICE_FEE_MODE="deduct", SERVICE_FEE_TYPE="flat", SERVICE_FEE_FLAT=Decimal("150")):
            self.assertEqual(fee_for_payment(Decimal("10000")).amount, Decimal("0.00"))
            self.assertEqual(quote_fee(Decimal("10000")).amount, Decimal("150.00"))


@override_settings(**ON_TOP)
class CheckoutTests(TestCase):
    def setUp(self):
        self.group = make_group(target="90000", members=2)  # three people, 30,000 each
        self.member = self.group.admin

    def test_the_contribution_records_the_fee_separately_from_the_share(self):
        c = initiate_contribution(self.group, self.member)
        self.assertEqual((c.amount, c.service_fee, c.charge_amount), (Decimal("30000.00"), Decimal("1500.00"), Decimal("31500.00")))

    def test_checkout_charges_share_plus_fee(self):
        c = initiate_contribution(self.group, self.member)
        with mock.patch.object(MockGateway, "initialize_payment", wraps=MockGateway().initialize_payment) as spy:
            services.start_checkout(c)
        self.assertEqual(spy.call_args.kwargs["amount"], Decimal("31500.00"))
        self.assertEqual(spy.call_args.kwargs["metadata"]["service_fee"], "1500.00")
        self.assertEqual(spy.call_args.kwargs["metadata"]["app"], "SPLITPAY")

    def test_only_the_share_counts_toward_the_pot(self):
        pay(self.group, self.member)
        self.assertEqual(total_funded(self.group), Decimal("30000.00"))
        self.assertEqual(self.group.memberships.get(user=self.member).outstanding, Decimal("0.00"))

    def test_paying_the_share_without_the_fee_is_not_accepted(self):
        c = initiate_contribution(self.group, self.member)
        services.confirm_contribution(c.reference, paid_amount=Decimal("30000"))
        c.refresh_from_db()
        self.assertEqual(c.status, ContributionStatus.FAILED)
        self.assertTrue(c.needs_review)
        self.assertEqual(total_funded(self.group), Decimal("0.00"))

    def test_paying_the_full_charge_is_accepted_and_the_paystack_fee_is_kept(self):
        c = initiate_contribution(self.group, self.member)
        services.confirm_contribution(c.reference, paid_amount=Decimal("31500"), gateway_fee=Decimal("572.50"))
        c.refresh_from_db()
        self.assertEqual((c.status, c.gateway_fee), (ContributionStatus.PAID, Decimal("572.50")))

    def test_a_stale_pending_checkout_is_repriced_when_the_policy_changes(self):
        c = initiate_contribution(self.group, self.member)
        c.checkout_url = "https://old.example/checkout"
        c.save()
        with override_settings(SERVICE_FEE_PERCENT=Decimal("4")):
            again = initiate_contribution(self.group, self.member)
        self.assertEqual(again.pk, c.pk)
        self.assertEqual(again.service_fee, Decimal("1200.00"))
        self.assertEqual(again.checkout_url, "")


@override_settings(**ON_TOP)
class PayoutAndLedgerTests(TestCase):
    def setUp(self):
        self.group = make_group(target="60000", members=1)  # two people, 30,000 each
        with self.captureOnCommitCallbacks(execute=True):
            for m in self.group.memberships.all():
                pay(self.group, m.user)
        self.group.refresh_from_db()

    def test_the_recipient_gets_the_full_pool_and_nothing_is_deducted(self):
        payout = Payout.objects.get()
        self.assertEqual((payout.gross_amount, payout.fee_amount, payout.net_amount),
                         (Decimal("60000.00"), Decimal("0.00"), Decimal("60000.00")))
        self.assertFalse(Fee.objects.exists())
        self.assertEqual(self.group.status, GroupStatus.PAID_OUT)

    def test_each_fee_is_its_own_ledger_line_paid_on_top(self):
        fee_rows = [e for e in ledger.group_entries(self.group) if e.kind == "fee"]
        self.assertEqual(sorted(e.amount for e in fee_rows), [Decimal("1500.00"), Decimal("1500.00")])
        self.assertTrue(all(e.detail["on_top"] for e in fee_rows))

    def test_the_summary_totals_the_fees_collected(self):
        summary = ledger.group_summary(self.group)
        self.assertEqual((summary["fee"], summary["net"]), (Decimal("3000.00"), Decimal("60000.00")))

    def test_the_receipt_says_the_fee_was_not_taken_from_the_payout(self):
        self.client.login(username=self.group.admin.email, password="pass12345!")
        html = self.client.get(reverse("web:group_receipt", args=[self.group.pk])).content.decode()
        self.assertIn("₦60,000.00", html)
        self.assertIn("₦3,000.00", html)
        self.assertIn("on top of their shares", html)

    def test_the_profit_and_loss_report_counts_the_fees_as_revenue(self):
        Contribution.objects.filter(group=self.group).update(gateway_fee=Decimal("572.50"))
        out = StringIO()
        call_command("splitpay_report", stdout=out)
        text = out.getvalue()
        self.assertIn("N3,000.00", text)  # revenue: 2 x 1,500 on top
        self.assertIn("N1,145.00", text)  # Paystack collection cost: 2 x 572.50
        self.assertIn("PROFIT", text)
        self.assertIn("N1,805.00", text)  # 3,000 - 1,145 - 50 transfer


@override_settings(**ON_TOP)
class PagesTests(TestCase):
    def setUp(self):
        self.group = make_group(target="90000", members=2)
        self.client.login(username=self.group.admin.email, password="pass12345!")

    def test_the_pay_button_shows_share_fee_and_total_before_paying(self):
        html = self.client.get(reverse("web:group_detail", args=[self.group.pk])).content.decode()
        self.assertIn("SplitPay service fee", html)
        self.assertIn("You pay today", html)
        self.assertIn("₦1,500.00", html)
        self.assertIn("Pay ₦31,500.00", html)

    def test_the_fees_page_explains_the_on_top_fee(self):
        html = self.client.get(reverse("web:pricing")).content.decode()
        self.assertIn("The recipient gets every naira", html)
        self.assertIn("₦157,500.00", html)  # a ₦150,000 share pays this

    def test_the_group_form_summary_shows_each_persons_total(self):
        html = self.client.get(reverse("web:group_new")).content.decode()
        self.assertIn("on_top: true", html)
        self.assertIn("Each person pays", html)

    def test_the_confirmation_screen_breaks_the_payment_down(self):
        c = initiate_contribution(self.group, self.group.admin)
        services.confirm_contribution(c.reference, paid_amount=c.charge_amount)
        html = self.client.get(reverse("web:contribution_confirmation", args=[c.reference])).content.decode()
        self.assertIn("₦31,500.00", html)
        self.assertIn("SplitPay service fee", html)

    def test_the_landing_page_explains_how_the_fee_works_with_live_numbers(self):
        self.client.logout()
        html = self.client.get(reverse("web:landing")).content.decode()
        self.assertIn("How our fee works", html)
        self.assertIn('id="our-fee"', html)
        self.assertIn("The recipient gets every naira", html)
        self.assertIn("₦10,500.00", html)   # a ₦10,000 share plus the 5% fee
        self.assertIn("₦600,000.00", html)  # four ₦150,000 shares reach the landlord in full
        self.assertIn("₦157,500.00", html)

    def test_the_landing_fee_section_is_hidden_when_the_fee_is_deducted_instead(self):
        self.client.logout()
        with override_settings(SERVICE_FEE_MODE="deduct"):
            html = self.client.get(reverse("web:landing")).content.decode()
        self.assertNotIn('id="our-fee"', html)

    def test_the_api_exposes_the_fee_and_the_total(self):
        client = APIClient()
        client.force_authenticate(self.group.admin)
        res = client.post(f"/api/v1/groups/{self.group.pk}/contribute/", {}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Decimal(res.data["contribution"]["service_fee"]), Decimal("1500.00"))
        self.assertEqual(Decimal(res.data["contribution"]["charge_amount"]), Decimal("31500.00"))
