from datetime import date, timedelta

from django.test import TestCase

from apps.groups.models import ContributionGroup, GroupStatus
from apps.groups.tasks import enforce_deadlines
from apps.notifications.models import Notification, NotificationDelivery
from apps.notifications.tasks import send_due_reminders
from apps.testing import make_group, pay


class ReminderTests(TestCase):
    def test_reminders_go_only_to_members_who_still_owe_and_are_not_repeated(self):
        group = make_group(target="90000", members=2)
        ContributionGroup.objects.filter(pk=group.pk).update(due_date=date.today() + timedelta(days=3))
        pay(group, group.admin)
        self.assertEqual(send_due_reminders(), 2)
        self.assertEqual(send_due_reminders(), 2)  # counted again, but deduplicated in the table
        self.assertEqual(Notification.objects.filter(kind="reminder").count(), 2)

    def test_no_reminder_outside_reminder_window(self):
        make_group(target="90000", members=2)  # due in 10 days
        self.assertEqual(send_due_reminders(), 0)

    def test_overdue_enforcement_flips_status_and_notifies(self):
        group = make_group(target="90000", members=2)
        ContributionGroup.objects.filter(pk=group.pk).update(due_date=date.today() - timedelta(days=1))
        self.assertEqual(enforce_deadlines(), 1)
        self.assertEqual(enforce_deadlines(), 0)
        group.refresh_from_db()
        self.assertEqual(group.status, GroupStatus.OVERDUE)
        self.assertEqual(Notification.objects.filter(kind="overdue").count(), 3)

    def test_every_notification_has_an_in_app_delivery_record(self):
        group = make_group(target="90000", members=1)
        pay(group, group.admin)
        for n in Notification.objects.all():
            self.assertEqual(n.deliveries.get().channel, "in_app")
            self.assertEqual(n.deliveries.get().status, NotificationDelivery.Status.SENT)
