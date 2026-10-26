"""Settle a failed bank-transfer payout by hand, with a proper audit trail.

Use it only when the payout cannot go out through Paystack (for example, Transfers are not yet
enabled on the Paystack business) and YOU have sent the money to the recipient yourself.

    python manage.py manual_payout 4                      # show who to pay and how much (changes nothing)
    python manage.py manual_payout 4 --confirm --reference "GTB-20261027-123456"

--confirm marks the payout completed, closes the group as paid out, notifies the members, and the
receipt then shows the reference you gave. It refuses payouts that are completed, or that Paystack
may still be processing (that could pay the recipient twice).
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.groups.models import ContributionGroup, PayoutType
from apps.payouts.models import Payout, PayoutStatus
from apps.payouts.services import _finish_transfer


class Command(BaseCommand):
    help = "Show, or record, a manual bank payout for a failed transfer."

    def add_arguments(self, parser):
        parser.add_argument("group_id", type=int)
        parser.add_argument("--confirm", action="store_true", help="Record that you have sent the money")
        parser.add_argument("--reference", default="", help="Your bank's transfer reference (required with --confirm)")
        parser.add_argument("--note", default="", help="Optional note kept with the payout")

    def handle(self, *args, group_id, confirm, reference, note, **opts):
        group = ContributionGroup.objects.filter(pk=group_id).first()
        if group is None:
            raise CommandError(f"No group with id {group_id}.")
        if group.payout_type != PayoutType.BANK_TRANSFER:
            raise CommandError("Only bank-transfer groups can be paid out by hand.")

        with transaction.atomic():
            payout = Payout.objects.select_for_update().filter(group=group).first()
            if payout is None:
                raise CommandError("This group has no payout yet. It must be funded (or paid out early) first.")
            if payout.status == PayoutStatus.COMPLETED:
                raise CommandError("This payout is already completed.")
            if payout.status != PayoutStatus.FAILED:
                raise CommandError(
                    f"The payout is '{payout.status}'. Only FAILED payouts can be settled by hand: "
                    "pending or processing ones may still be sent by Paystack and would be paid twice.")

            self.stdout.write(f"Group #{group.pk}  {group.name}   payout status: {payout.status}")
            self.stdout.write(f"  Send exactly   N{payout.net_amount:,.2f}")
            self.stdout.write(f"  To             {payout.recipient_account_name}")
            self.stdout.write(f"  Bank           {payout.recipient_bank_name} ({payout.recipient_bank_code})")
            self.stdout.write(f"  Account no.    {payout.recipient_account_number}")
            self.stdout.write(f"  Last failure   {payout.failure_reason or '-'}")

            if not confirm:
                self.stdout.write("\nNothing was changed. After you have sent the money, run:")
                self.stdout.write(f'  python manage.py manual_payout {group.pk} --confirm --reference "<your bank reference>"')
                return
            if not reference.strip():
                raise CommandError("--reference is required with --confirm: use your bank's transfer reference.")

            payout.gateway = "manual"
            payout.gateway_reference = reference.strip()[:100]
            payout.failure_reason = (f"Settled manually. {note}".strip())[:250] if note else ""
            payout.save(update_fields=["gateway", "gateway_reference", "failure_reason", "updated_at"])
            _finish_transfer(payout.pk, PayoutStatus.COMPLETED)

        self.stdout.write(self.style.SUCCESS(
            f"Recorded: group #{group.pk} is now paid out (reference {reference.strip()}). Members were notified."))
