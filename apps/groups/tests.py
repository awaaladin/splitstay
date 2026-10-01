from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from rest_framework.test import APIClient

from apps.groups import services
from apps.groups.models import GroupStatus
from apps.testing import make_group, make_user, pay


class ShareSplitTests(TestCase):
    def shares(self, group):
        return [m.contribution_share for m in group.memberships.exclude(status="left").order_by("id")]

    def test_equal_split_sums_exactly_to_target_with_kobo_remainder(self):
        group = make_group(target="100000.00", members=2)  # 3 ways => 33,333.34 / 33,333.33 / 33,333.33
        shares = self.shares(group)
        self.assertEqual(sum(shares), Decimal("100000.00"))
        self.assertEqual(sorted(shares), [Decimal("33333.33"), Decimal("33333.33"), Decimal("33333.34")])

    def test_custom_share_is_kept_and_rest_split_equally(self):
        group = make_group(target="100000", members=2)
        other = group.memberships.exclude(user=group.admin).first().user
        services.set_member_share(group, other, Decimal("60000"))
        shares = self.shares(group)
        self.assertEqual(sum(shares), Decimal("100000.00"))
        self.assertIn(Decimal("60000.00"), shares)
        self.assertEqual(sorted(shares)[:2], [Decimal("20000.00"), Decimal("20000.00")])

    def test_custom_shares_cannot_exceed_target(self):
        group = make_group(target="100000", members=2)
        other = group.memberships.exclude(user=group.admin).first().user
        with self.assertRaises(ValidationError):
            services.set_member_share(group, other, Decimal("150000"))

    def test_membership_locked_after_first_payment(self):
        group = make_group(target="90000", members=2)
        pay(group, group.admin)
        with self.assertRaises(ValidationError):
            services.add_member(group, make_user())

    def test_remove_member_rebalances(self):
        group = make_group(target="90000", members=2)
        victim = group.memberships.exclude(user=group.admin).first().user
        services.remove_member(group, victim)
        active = group.memberships.exclude(status="left")
        self.assertEqual(active.count(), 2)
        self.assertEqual(active.aggregate(t=Sum("contribution_share"))["t"], Decimal("90000.00"))

    def test_cancel_blocked_once_money_received(self):
        group = make_group(target="90000", members=2)
        pay(group, group.admin)
        with self.assertRaises(ValidationError):
            services.cancel_group(group)
        group.refresh_from_db()
        self.assertEqual(group.status, GroupStatus.OPEN)


class GroupApiPermissionTests(TestCase):
    def setUp(self):
        self.group = make_group(target="90000", members=2)
        self.admin = self.group.admin
        self.member = self.group.memberships.exclude(user=self.admin).first().user
        self.outsider = make_user("Outsider")
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_outsider_cannot_see_group_or_ledger(self):
        c = self.as_user(self.outsider)
        self.assertEqual(c.get(f"/api/v1/groups/{self.group.pk}/").status_code, 404)
        self.assertEqual(c.get(f"/api/v1/groups/{self.group.pk}/ledger/").status_code, 404)
        self.assertEqual(c.get(f"/api/v1/ledger/groups/{self.group.pk}/").status_code, 403)

    def test_any_member_can_read_ledger_not_only_admin(self):
        pay(self.group, self.admin)
        res = self.as_user(self.member).get(f"/api/v1/groups/{self.group.pk}/ledger/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["results"][0]["kind"], "contribution")
        self.assertEqual(len(res.data["members"]), 3)
        self.assertEqual(res.data["summary"]["funded"], Decimal("30000.00"))

    def test_invited_user_cannot_read_ledger_until_joined(self):
        invitee = make_user("Invitee")
        services.add_member(self.group, invitee)
        c = self.as_user(invitee)
        self.assertEqual(c.get(f"/api/v1/groups/{self.group.pk}/").status_code, 200)
        self.assertEqual(c.get(f"/api/v1/groups/{self.group.pk}/ledger/").status_code, 403)

    def test_only_admin_can_edit_payout_cancel_or_remove(self):
        c = self.as_user(self.member)
        gid = self.group.pk
        self.assertEqual(c.patch(f"/api/v1/groups/{gid}/", {"name": "Hacked"}, format="json").status_code, 403)
        self.assertEqual(c.post(f"/api/v1/groups/{gid}/payout/").status_code, 403)
        self.assertEqual(c.post(f"/api/v1/groups/{gid}/cancel/").status_code, 403)
        self.assertEqual(c.delete(f"/api/v1/groups/{gid}/members/{self.admin.pk}/").status_code, 403)
        self.assertEqual(c.post(f"/api/v1/groups/{gid}/members/", {"identifier": "x@y.com"}, format="json").status_code, 403)

    def test_admin_can_edit_group(self):
        res = self.as_user(self.admin).patch(f"/api/v1/groups/{self.group.pk}/", {"name": "New name"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["name"], "New name")

    def test_contribute_only_pays_own_share(self):
        res = self.as_user(self.member).post(f"/api/v1/groups/{self.group.pk}/contribute/", {}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["contribution"]["member"]["id"], self.member.pk)
        self.assertEqual(Decimal(res.data["contribution"]["amount"]), Decimal("30000.00"))
        self.assertIn("checkout_url", res.data)

    def test_partial_payout_refused_unless_group_allows(self):
        pay(self.group, self.admin)
        res = self.as_user(self.admin).post(f"/api/v1/groups/{self.group.pk}/payout/")
        self.assertEqual(res.status_code, 400)

    def test_group_list_is_paginated_and_scoped(self):
        make_group(target="5000", members=1)  # someone else's group
        res = self.as_user(self.admin).get("/api/v1/groups/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        self.assertIn("results", res.data)
