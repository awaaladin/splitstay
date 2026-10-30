"""The service fee rate follows the group's target: 5% up to N1M, 4% up to N10M, 3% above."""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.contributions.services import initiate_contribution
from apps.payouts.fees import fee_for_payment, quote_fee, rate_for_pot
from apps.testing import make_group

TIERS = [(Decimal("1000000"), Decimal("5")), (Decimal("10000000"), Decimal("4")), (None, Decimal("3"))]
TIERED = dict(SERVICE_FEE_MODE="on_top", SERVICE_FEE_TYPE="percent", SERVICE_FEE_TIERS=TIERS,
              SERVICE_FEE_MIN=Decimal("0"), SERVICE_FEE_MAX=Decimal("0"))


@override_settings(**TIERED)
class TierTests(TestCase):
    def test_each_limit_belongs_to_its_tier(self):
        for pot, rate in (("1", "5"), ("1000000", "5"), ("1000000.01", "4"), ("10000000", "4"),
                          ("10000000.01", "3"), ("50000000", "3")):
            self.assertEqual(rate_for_pot(Decimal(pot)), Decimal(rate), pot)

    def test_fee_is_a_percent_of_the_payment_at_the_groups_rate(self):
        self.assertEqual(fee_for_payment(Decimal("150000"), Decimal("600000")).amount, Decimal("7500.00"))
        self.assertEqual(fee_for_payment(Decimal("750000"), Decimal("3000000")).amount, Decimal("30000.00"))
        self.assertEqual(fee_for_payment(Decimal("5000000"), Decimal("20000000")).amount, Decimal("150000.00"))

    def test_payouts_still_deduct_nothing(self):
        self.assertEqual(quote_fee(Decimal("20000000")).amount, Decimal("0.00"))

    @override_settings(SERVICE_FEE_PER_PAYMENT=Decimal("100"))
    def test_optional_per_payment_charge_is_added(self):
        self.assertEqual(fee_for_payment(Decimal("2500"), Decimal("50000")).amount, Decimal("225.00"))


@override_settings(**TIERED)
class TieredCheckoutTests(TestCase):
    def test_a_big_group_is_charged_the_lower_rate(self):
        group = make_group(target="3000000", members=2)
        member = group.memberships.exclude(user=group.admin).first().user
        contribution = initiate_contribution(group, member)
        self.assertEqual(contribution.service_fee, contribution.amount * Decimal("0.04"))

    def test_the_api_quote_matches_what_is_charged(self):
        group = make_group(target="20000000", members=2)
        member = group.memberships.exclude(user=group.admin).first().user
        client = APIClient()
        client.force_authenticate(member)
        quote = client.get(f"/api/v1/groups/{group.pk}/").data["pay_quote"]
        contribution = initiate_contribution(group, member)
        self.assertEqual(Decimal(quote["fee"]), contribution.service_fee)
        self.assertEqual(Decimal(quote["total"]), contribution.charge_amount)


@override_settings(**TIERED)
class FeesPageTests(TestCase):
    def test_page_explains_the_tiers_and_how_payment_is_collected(self):
        html = self.client.get(reverse("web:pricing")).content.decode()
        for phrase in ("Up to ₦1,000,000", "₦1,000,000 to ₦10,000,000", "Above ₦10,000,000", "How we collect payment", "Paystack's secure checkout"):
            self.assertIn(phrase, html)
