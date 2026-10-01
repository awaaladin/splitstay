from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.groups import services as group_services
from apps.groups.models import ContributionGroup, GroupStatus
from apps.notifications.models import Notification
from apps.recurrence.services import due_date_for_cycle, spawn_next_cycle
from apps.recurrence.tasks import spawn_due_cycles
from apps.testing import make_group, pay


def recurring_group(**overrides):
    fields = dict(
        name="Family light bill", purpose="electricity", target_amount=Decimal("60000"),
        is_recurring=True, recurrence_interval="monthly", due_date=date(2030, 1, 31),
        payout_type="bill_payment", bill_service_id="ikeja-electric", bill_customer_id="45012345678",
        bill_variation="prepaid", recipient_bank_code="", recipient_account_number="",
    )
    fields.update(overrides)
    return make_group(target=fields.pop("target_amount"), members=2, **fields)


class RecurrenceTests(TestCase):
    def test_next_cycle_keeps_members_split_and_settings(self):
        group = recurring_group()
        other = group.memberships.exclude(user=group.admin).first().user
        group_services.set_member_share(group, other, Decimal("30000"))
        new = spawn_next_cycle(group)
        self.assertIsNotNone(new)
        self.assertEqual(new.status, GroupStatus.OPEN)
        self.assertEqual(new.cycle_number, 2)
        self.assertEqual(new.previous_cycle, group)
        for field in ("name", "target_amount", "payout_type", "bill_service_id", "bill_customer_id", "admin_id"):
            self.assertEqual(getattr(new, field), getattr(group, field))
        old = {m.user_id: (m.contribution_share, m.is_custom_share, m.status) for m in group.memberships.all()}
        cloned = {m.user_id: (m.contribution_share, m.is_custom_share, m.status) for m in new.memberships.all()}
        self.assertEqual(old, cloned)
        self.assertEqual(Notification.objects.filter(kind="cycle", group=new).count(), 3)

    def test_new_cycle_starts_with_zero_contributions(self):
        group = recurring_group()
        pay(group, group.admin)
        new = spawn_next_cycle(group)
        self.assertEqual(new.total_funded, Decimal("0.00"))
        self.assertEqual(group.total_funded, Decimal("20000.00"))

    def test_due_dates_hold_the_day_of_month(self):
        group = recurring_group(due_date=date(2030, 1, 31))
        self.assertEqual(due_date_for_cycle(group, 1), date(2030, 1, 31))
        self.assertEqual(due_date_for_cycle(group, 2), date(2030, 2, 28))
        self.assertEqual(due_date_for_cycle(group, 3), date(2030, 3, 31))  # not 28 Mar
        self.assertEqual(due_date_for_cycle(group, 4), date(2030, 4, 30))

    def test_quarterly_and_annual_intervals(self):
        quarterly = recurring_group(recurrence_interval="quarterly", due_date=date(2030, 1, 15))
        self.assertEqual(due_date_for_cycle(quarterly, 2), date(2030, 4, 15))
        annual = recurring_group(recurrence_interval="annual", due_date=date(2030, 2, 28))
        self.assertEqual(due_date_for_cycle(annual, 3), date(2032, 2, 28))

    def test_spawning_twice_creates_only_one_successor(self):
        group = recurring_group()
        self.assertIsNotNone(spawn_next_cycle(group))
        self.assertIsNone(spawn_next_cycle(group))
        self.assertEqual(ContributionGroup.objects.filter(previous_cycle=group).count(), 1)

    def test_non_recurring_and_cancelled_groups_do_not_spawn(self):
        one_off = make_group(target="30000", members=1)
        self.assertIsNone(spawn_next_cycle(one_off))
        cancelled = recurring_group()
        group_services.cancel_group(cancelled)
        self.assertIsNone(spawn_next_cycle(cancelled))

    def test_task_spawns_for_paid_out_group(self):
        group = recurring_group(due_date=date.today() + timedelta(days=20))
        ContributionGroup.objects.filter(pk=group.pk).update(status=GroupStatus.PAID_OUT)
        self.assertEqual(spawn_due_cycles(), 1)
        self.assertEqual(spawn_due_cycles(), 0)  # re-running the beat task is harmless
        self.assertTrue(ContributionGroup.objects.filter(previous_cycle=group).exists())

    def test_task_spawns_when_due_date_passes_even_if_unpaid(self):
        group = recurring_group(due_date=date.today() + timedelta(days=5))
        self.assertEqual(spawn_due_cycles(today=date.today()), 0)  # still open and not yet due
        self.assertEqual(spawn_due_cycles(today=date.today() + timedelta(days=6)), 1)
        self.assertTrue(ContributionGroup.objects.filter(previous_cycle=group).exists())

    def test_task_ignores_open_group_before_due_date(self):
        recurring_group(due_date=date.today() + timedelta(days=15))
        self.assertEqual(spawn_due_cycles(), 0)

    def test_task_skips_cancelled_recurring_group(self):
        group = recurring_group(due_date=date.today() - timedelta(days=3))
        group_services.cancel_group(group)
        self.assertEqual(spawn_due_cycles(), 0)

    def test_chain_of_cycles_counts_up(self):
        group = recurring_group()
        second = spawn_next_cycle(group)
        third = spawn_next_cycle(second)
        self.assertEqual((second.cycle_number, third.cycle_number), (2, 3))
        self.assertEqual(third.due_date, date(2030, 3, 31))
