"""Create demo users and three demo groups (rent, NEPA bill, family upkeep) with real contributions.

Everything goes through the same services the app uses, so the seeded data is exactly what the
product would have produced: shares, fees, a completed bill payment with a token, a recurring rent
group, and a partly-funded family group that allows early payout.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.contributions.models import Contribution
from apps.groups import services as group_services
from apps.groups.models import ContributionGroup
from apps.testing import pay

DEMO_DOMAIN = "demo.splitstay.test"
PASSWORD = "demo12345"

PEOPLE = [
    ("ada", "Ada Okafor", "+2348030000001"),
    ("tunde", "Tunde Bello", "+2348030000002"),
    ("chioma", "Chioma Eze", "+2348030000003"),
    ("ibrahim", "Ibrahim Musa", "+2348030000004"),
    ("ngozi", "Ngozi Adeyemi", "+2348030000005"),
]


class Command(BaseCommand):
    help = "Seed demo users and groups for local testing. Use --reset to wipe and recreate."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, **opts):
        User = get_user_model()
        if opts["reset"]:
            self._wipe(User)
        elif User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}").exists():
            self.stdout.write(self.style.WARNING("Demo data already exists. Re-run with --reset to recreate it."))
            return

        # Run payouts inline so seeding works without a Celery worker or Redis.
        from config.celery import app as celery_app

        previous = celery_app.conf.task_always_eager
        celery_app.conf.task_always_eager = True
        try:
            users = self._users(User)
            self._rent(users)
            self._nepa(users)
            self._family(users)
        finally:
            celery_app.conf.task_always_eager = previous

        self.stdout.write(self.style.SUCCESS("Demo data created."))
        self.stdout.write(f"  Sign in as ada@{DEMO_DOMAIN} / {PASSWORD}  (admin of all three groups)")
        self.stdout.write(f"  Others: tunde@, chioma@, ibrahim@, ngozi@{DEMO_DOMAIN}, same password")

    # ------------------------------------------------------------------
    def _wipe(self, User):
        demo = User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}")
        groups = ContributionGroup.objects.filter(admin__in=demo)
        # Contributions/payouts use PROTECT on purpose; a reset is the one place we clear them.
        from apps.billpay.models import BillPayment
        from apps.payouts.models import Payout

        chain = ContributionGroup.objects.filter(admin__in=demo).order_by("-cycle_number")
        for g in chain:
            Contribution.objects.filter(group=g).delete()
            Payout.objects.filter(group=g).delete()
            BillPayment.objects.filter(group=g).delete()
        for g in chain:
            g.previous_cycle = None
            g.save(update_fields=["previous_cycle"])
        groups.delete()
        demo.delete()
        self.stdout.write("Removed previous demo data.")

    def _users(self, User):
        users = {}
        for handle, name, phone in PEOPLE:
            user = User.objects.create_user(email=f"{handle}@{DEMO_DOMAIN}", password=PASSWORD)
            user.profile.full_name = name
            user.profile.phone_number = phone
            user.profile.save()
            users[handle] = user
        return users

    def _join_all(self, group):
        for m in group.memberships.filter(status="invited"):
            group_services.accept_invitation(group, m.user)

    def _settle(self, group):
        """Run a funded group's payout now instead of waiting for the Celery task (which is idempotent)."""
        from apps.billpay.services import execute_bill_payment
        from apps.payouts.services import execute_transfer, get_payout_record

        group.refresh_from_db()
        record = get_payout_record(group)
        if record is not None and record.status == "pending":
            (execute_bill_payment if hasattr(record, "service_id") else execute_transfer)(record.pk)

    def _backdate(self, contribution, days_ago, hour=10):
        when = timezone.now().replace(hour=hour, minute=12, second=0, microsecond=0) - timedelta(days=days_ago)
        Contribution.objects.filter(pk=contribution.pk).update(created_at=when, paid_at=when)

    def _rent(self, u):
        """Recurring monthly rent to a landlord's account. Uneven split, 3 of 4 paid."""
        group = group_services.create_group(
            admin=u["ada"], name="Flat 4B Rent", purpose="rent", target_amount=Decimal("600000"),
            description="Monthly house-rent contribution for the four of us. Landlord: Adewale Properties Ltd.",
            due_date=date.today() + timedelta(days=9), is_recurring=True, recurrence_interval="monthly",
            payout_type="bank_transfer", recipient_bank_code="058", recipient_bank_name="Guaranty Trust Bank",
            recipient_account_name="Adewale Properties Ltd", recipient_account_number="0123456789",
            members=[(u["tunde"], Decimal("200000")), (u["chioma"], None), (u["ibrahim"], None)],
        )
        self._join_all(group)
        for days, handle in ((6, "ada"), (4, "tunde"), (2, "chioma")):
            self._backdate(pay(group, u[handle]), days)

    def _nepa(self, u):
        """Electricity bill, fully funded and paid: a completed receipt with a token."""
        group = group_services.create_group(
            admin=u["ada"], name="Lekki Flat Electricity", purpose="electricity", target_amount=Decimal("30000"),
            description="Prepaid meter for the flat. Top-up once a month.",
            due_date=date.today() + timedelta(days=4), is_recurring=True, recurrence_interval="monthly",
            payout_type="bill_payment", bill_service_id="eko-electric", bill_customer_id="45012345678", bill_variation="prepaid",
            members=[(u["tunde"], None), (u["ngozi"], None)],
        )
        self._join_all(group)
        for offset, handle in enumerate(("ngozi", "tunde", "ada")):
            self._backdate(pay(group, u[handle]), 5 - offset * 2)
        self._settle(group)

    def _family(self, u):
        """Family upkeep with custom shares, one invitation pending, early payout allowed."""
        group = group_services.create_group(
            admin=u["ada"], name="Mama's Monthly Upkeep", purpose="family_upkeep", target_amount=Decimal("150000"),
            description="Monthly upkeep for Mama in Enugu. Sent straight to her account.",
            due_date=date.today() + timedelta(days=14), is_recurring=True, recurrence_interval="monthly",
            allow_partial_payout=True, payout_type="bank_transfer", recipient_bank_code="044",
            recipient_bank_name="Access Bank", recipient_account_name="Ngozi Okafor", recipient_account_number="0987654321",
            members=[(u["ibrahim"], Decimal("30000")), (u["chioma"], Decimal("30000")), (u["ngozi"], None)],
        )
        for m in group.memberships.filter(status="invited").exclude(user=u["ngozi"]):
            group_services.accept_invitation(group, m.user)
        # Ngozi has been invited but hasn't joined yet, so her invitation shows on her dashboard.
        for days, handle in ((3, "ada"), (1, "ibrahim")):
            self._backdate(pay(group, u[handle]), days, hour=15)
