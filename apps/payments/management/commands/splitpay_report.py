"""Profit and loss for SplitPay on the shared Paystack account.

    python manage.py splitpay_report                      # all time
    python manage.py splitpay_report --from 2026-11-01 --to 2026-11-30
    python manage.py splitpay_report --csv splitpay.csv   # one row per Paystack reference

Everything here comes from SplitPay's own records, so it covers only SplitPay's references
(SPLITPAY-... / splitpay-...), however many other apps share the Paystack account.

  Revenue  = SplitPay service fees on payouts that actually went out.
  Costs    = Paystack's charge on each collection (recorded from Paystack, exact) plus the transfer
             fee on each payout (ESTIMATED from Paystack's published tiers in settings).
  Held     = member money collected but not yet paid out. It is NOT revenue.
"""
import csv
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Sum
from django.utils import timezone

from apps.billpay.models import BillPayment
from apps.contributions.models import Contribution, ContributionStatus
from apps.payouts.models import Payout, PayoutStatus

ZERO = Decimal("0.00")


def naira(value) -> str:
    return f"N{Decimal(value or 0):,.2f}"


def transfer_fee(amount: Decimal) -> Decimal:
    for ceiling, fee in settings.PAYSTACK_TRANSFER_FEES:
        if ceiling is None or amount <= ceiling:
            return fee
    return ZERO


class Command(BaseCommand):
    help = "SplitPay profit/loss: fees earned vs. Paystack costs, plus money still held for groups."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", help="YYYY-MM-DD (inclusive)")
        parser.add_argument("--to", dest="end", help="YYYY-MM-DD (inclusive)")
        parser.add_argument("--csv", help="Also write one row per transaction to this file")

    def _bounds(self, opts):
        tz = timezone.get_current_timezone()
        try:
            start = datetime.strptime(opts["start"], "%Y-%m-%d") if opts["start"] else None
            end = datetime.strptime(opts["end"], "%Y-%m-%d") if opts["end"] else None
        except ValueError as exc:
            raise CommandError("Dates must look like 2026-11-30") from exc
        start = timezone.make_aware(datetime.combine(start, time.min), tz) if start else None
        end = timezone.make_aware(datetime.combine(end, time.max), tz) if end else None
        return start, end

    def handle(self, *args, **opts):
        start, end = self._bounds(opts)

        def within(qs, field):
            if start:
                qs = qs.filter(**{f"{field}__gte": start})
            if end:
                qs = qs.filter(**{f"{field}__lte": end})
            return qs

        paid = within(Contribution.objects.filter(status=ContributionStatus.PAID), "paid_at")
        collected = paid.aggregate(total=Sum("amount"), fees=Sum("gateway_fee"), n=Count("id"))
        unknown_fee_rows = paid.filter(gateway_fee__isnull=True).count()

        done_payouts = list(within(Payout.objects.filter(status=PayoutStatus.COMPLETED), "completed_at"))
        done_bills = list(within(BillPayment.objects.filter(status=PayoutStatus.COMPLETED), "completed_at"))
        revenue = sum((r.fee_amount for r in done_payouts + done_bills), ZERO)
        transfer_costs = sum((transfer_fee(p.net_amount) for p in done_payouts), ZERO)
        paid_out = sum((r.net_amount for r in done_payouts + done_bills), ZERO)

        collection_costs = collected["fees"] or ZERO
        costs = collection_costs + transfer_costs
        profit = revenue - costs

        pending_payouts = list(Payout.objects.exclude(status=PayoutStatus.COMPLETED)) + list(
            BillPayment.objects.exclude(status=PayoutStatus.COMPLETED))
        in_flight = sum((r.net_amount for r in pending_payouts), ZERO)
        all_paid = Contribution.objects.filter(status=ContributionStatus.PAID).aggregate(t=Sum("amount"))["t"] or ZERO
        all_out = sum((r.gross_amount for r in list(Payout.objects.filter(status=PayoutStatus.COMPLETED))
                       + list(BillPayment.objects.filter(status=PayoutStatus.COMPLETED))), ZERO)
        held = all_paid - all_out

        window = f"{opts['start'] or 'start'} to {opts['end'] or 'today'}"
        out = self.stdout.write
        out(f"SplitPay profit & loss ({window})")
        out("-" * 58)
        out(f"Collected from members    {naira(collected['total']):>18}   ({collected['n']} payments)")
        out(f"Paid out to recipients    {naira(paid_out):>18}   ({len(done_payouts)} transfers, {len(done_bills)} bills)")
        out("")
        out(f"Revenue: service fees     {naira(revenue):>18}")
        out(f"Cost: Paystack collection {naira(collection_costs):>18}   (actual, from Paystack)")
        out(f"Cost: Paystack transfers  {naira(transfer_costs):>18}   (estimated from published tiers)")
        label = "PROFIT" if profit >= 0 else "LOSS  "
        out(f"{label}                    {naira(abs(profit)):>18}")
        out("-" * 58)
        out(f"Member money still held   {naira(held):>18}   (collected, not yet paid out; not revenue)")
        out(f"  of which payouts in flight {naira(in_flight):>15}")
        if unknown_fee_rows:
            out(self.style.WARNING(
                f"\n{unknown_fee_rows} paid contribution(s) have no recorded Paystack fee, so collection costs "
                "are understated. Fees fill in when Paystack confirms the payment."))

        if opts["csv"]:
            with open(opts["csv"], "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["type", "reference", "group", "date", "amount", "service_fee", "paystack_fee", "status"])
                for c in paid.select_related("group"):
                    w.writerow(["collection", c.reference, c.group.name, c.paid_at.date(), c.amount, "", c.gateway_fee or "", c.status])
                for p in done_payouts:
                    w.writerow(["transfer", p.reference, p.group.name, p.completed_at.date(), p.net_amount, p.fee_amount,
                                transfer_fee(p.net_amount), p.status])
                for b in done_bills:
                    w.writerow(["bill", b.reference, b.group.name, b.completed_at.date(), b.net_amount, b.fee_amount, "", b.status])
            out(f"\nWrote {opts['csv']}")
