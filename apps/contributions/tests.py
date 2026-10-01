from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.contributions.models import Contribution, ContributionStatus
from apps.contributions.selectors import progress, total_funded
from apps.contributions.services import initiate_contribution
from apps.groups.models import ContributionGroup
from apps.testing import make_group, pay


class ContributionTotalTests(TestCase):
    def setUp(self):
        self.group = make_group(target="90000", members=2)  # admin + 2 => 30,000 each
        self.admin, self.a, self.b = [m.user for m in self.group.memberships.order_by("id")]

    def test_total_is_zero_with_no_contributions(self):
        self.assertEqual(total_funded(self.group), Decimal("0.00"))

    def test_total_sums_only_paid_contributions(self):
        pay(self.group, self.admin)
        pay(self.group, self.a, Decimal("10000"))
        # pending and failed rows must never count toward the total
        Contribution.objects.create(group=self.group, member=self.b, amount=Decimal("30000"))
        Contribution.objects.create(
            group=self.group, member=self.b, amount=Decimal("5000"), status=ContributionStatus.FAILED
        )
        self.assertEqual(total_funded(self.group), Decimal("40000.00"))

    def test_total_is_derived_not_stored(self):
        field_names = {f.name for f in ContributionGroup._meta.get_fields()}
        self.assertFalse({"total_funded", "funded_amount", "amount_raised", "current_amount"} & field_names)
        pay(self.group, self.admin)
        # the model property and the selector agree, and both track the rows
        self.assertEqual(self.group.total_funded, Decimal("30000.00"))
        Contribution.objects.filter(group=self.group).update(status=ContributionStatus.FAILED)
        self.assertEqual(self.group.total_funded, Decimal("0.00"))

    def test_progress_percent_and_remaining(self):
        pay(self.group, self.admin)
        data = progress(self.group)
        self.assertEqual(data["percent"], Decimal("33.3"))
        self.assertEqual(data["remaining"], Decimal("60000.00"))
        self.assertFalse(data["is_funded"])

    def test_member_cannot_overpay_their_share(self):
        with self.assertRaises(ValidationError):
            initiate_contribution(self.group, self.admin, Decimal("30000.01"))

    def test_partial_payments_reduce_outstanding(self):
        pay(self.group, self.a, Decimal("12000"))
        m = self.group.memberships.get(user=self.a)
        self.assertEqual(m.outstanding, Decimal("18000.00"))

    def test_reclicking_pay_reuses_pending_contribution(self):
        first = initiate_contribution(self.group, self.a)
        second = initiate_contribution(self.group, self.a)
        self.assertEqual(first.pk, second.pk)
