"""Server-rendered pages. Every view calls the same service layer the REST API uses, so the rules
(who can pay what, when a group is funded, how fees are taken) exist in exactly one place."""
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import BankAccount
from apps.billpay import services as bill_services
from apps.billpay.providers import BillProviderUnavailable
from apps.contributions.models import Contribution, ContributionStatus
from apps.contributions import services as contribution_services
from apps.contributions.selectors import progress as group_progress
from apps.groups import selectors, services as group_services
from apps.groups.models import ContributionGroup, GroupStatus, MembershipStatus, PayoutType
from apps.ledger import services as ledger
from apps.notifications import services as notification_services
from apps.notifications.models import Notification
from apps.payments import services as payment_services
from apps.payments.gateways import GatewayError
from apps.payouts import services as payout_services

from .forms import BankAccountForm, GroupForm, InviteForm, LoginForm, ProfileForm, RegisterForm


# --- helpers ------------------------------------------------------------------------

def visible_group(request, pk) -> ContributionGroup:
    """404 for anyone who is not the admin / an invitee / a member (never reveals a group exists)."""
    return get_object_or_404(selectors.groups_visible_to(request.user), pk=pk)


def member_only_group(request, pk) -> ContributionGroup:
    group = visible_group(request, pk)
    if not selectors.is_member(group, request.user):
        raise Http404
    return group


def admin_only_group(request, pk) -> ContributionGroup:
    group = visible_group(request, pk)
    if group.admin_id != request.user.pk:
        raise Http404
    return group


def flash_errors(request, exc: ValidationError):
    for message in exc.messages:
        messages.error(request, message)


def is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def pot_geometry(prog: dict, initial: bool) -> dict:
    """Numbers the pot template needs. `initial` renders empty so the JS can fill it after the boot screen."""
    percent = float(prog["percent"])
    empty = round(100 - percent, 1)
    return {"percent_value": percent, "empty_value": empty}


def group_page_context(request, group: ContributionGroup, *, initial: bool = False) -> dict:
    user = request.user
    membership = selectors.get_membership(group, user)
    is_admin = group.admin_id == user.pk
    is_member = selectors.is_member(group, user)
    ctx = {
        "group": group, "membership": membership, "is_admin": is_admin, "is_member": is_member,
        "is_invited": bool(membership and membership.status == MembershipStatus.INVITED and not is_admin),
        "initial": initial,
    }
    if not is_member:
        return ctx
    prog = group_progress(group)
    record = payout_services.get_payout_record(group)
    rows = ledger.member_rows(group)
    my_row = next((r for r in rows if r["user"].pk == user.pk), None)
    is_bill = group.payout_type == PayoutType.BILL_PAYMENT
    can_pay = bool(
        group.is_open_for_contributions and membership and membership.status == MembershipStatus.JOINED
        and my_row and my_row["outstanding"] > 0
    )
    ctx.update(
        progress=prog, **pot_geometry(prog, initial), rows=rows, my_row=my_row,
        entries=ledger.group_entries(group)[:10], record=record, is_bill=is_bill,
        contributors=sum(1 for r in rows if r["paid"] > 0), can_pay=can_pay,
        can_partial_payout=bool(
            is_admin and group.allow_partial_payout and group.is_open_for_contributions
            and prog["funded"] > 0 and record is None
        ),
        can_retry=bool(is_admin and record is not None and record.status == "failed"),
        can_edit=is_admin and group.is_open_for_contributions,
        can_manage_members=is_admin and group.is_open_for_contributions and prog["funded"] == 0,
        can_cancel=is_admin and group.status in (GroupStatus.OPEN, GroupStatus.OVERDUE) and prog["funded"] == 0,
        invite_form=InviteForm(),
        needs_review=group.contributions.filter(needs_review=True).exists() if is_admin else False,
    )
    return ctx


# --- public + auth ----------------------------------------------------------------------

def landing(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    return render(request, "landing.html")


def guide(request):
    """The complete start-to-finish user guide. Public, and also linked from the signed-in nav."""
    return render(request, "guide.html")


def about(request):
    return render(request, "pages/about.html")


def pricing(request):
    """Fees page. Examples are computed from the live fee settings, so the page can't drift from reality."""
    from apps.payouts.fees import quote_fee

    examples = []
    for pool in (Decimal("30000"), Decimal("150000"), Decimal("600000")):
        quote = quote_fee(pool)
        examples.append({"pool": pool, "fee": quote.amount, "net": quote.net(pool)})
    return render(request, "pages/pricing.html", {"fee": _fee_policy(), "examples": examples})


def privacy(request):
    return render(request, "pages/privacy.html")


def terms(request):
    return render(request, "pages/terms.html")


def contact(request):
    from django.core.cache import cache

    from .forms import ContactForm
    from .models import ContactMessage

    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.display_name, "email": request.user.email}
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")).split(",")[0].strip()
        key = f"contact:{ip}"
        sent = cache.get(key, 0)
        if sent >= 5:
            messages.error(request, "You've sent several messages in a short time. Please try again in an hour.")
        else:
            cache.set(key, sent + 1, 3600)
            data = form.cleaned_data
            ContactMessage.objects.create(
                name=data["name"], email=data["email"], topic=data["topic"], message=data["message"],
                reference=data.get("reference", ""), user=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, "Thanks. Your message has been received and we'll reply by email.")
            return redirect("web:contact")
    return render(request, "pages/contact.html", {"form": form})


def register(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(email=form.cleaned_data["email"], password=form.cleaned_data["password"])
        user.profile.full_name = form.cleaned_data["full_name"]
        user.profile.phone_number = form.cleaned_data["phone_number"]
        user.profile.save()
        login(request, user, backend="apps.accounts.backends.EmailOrPhoneBackend")
        messages.success(request, "Welcome to SplitStay. Your account is ready.")
        return redirect("web:dashboard")
    return render(request, "auth/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    form = LoginForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        login(request, form.user, backend="apps.accounts.backends.EmailOrPhoneBackend")
        next_url = request.GET.get("next", "")
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect("web:dashboard")
    return render(request, "auth/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("web:landing")


# --- dashboard ------------------------------------------------------------------------------

@login_required
def dashboard(request):
    user = request.user
    groups = list(selectors.groups_visible_to(user).order_by("due_date"))
    ids = [g.pk for g in groups]
    funded = {
        row["group_id"]: row["t"]
        for row in Contribution.objects.filter(group_id__in=ids, status="paid").values("group_id").annotate(t=Sum("amount"))
    }
    mine = {
        row["group_id"]: row["t"]
        for row in Contribution.objects.filter(group_id__in=ids, member=user, status="paid").values("group_id").annotate(t=Sum("amount"))
    }
    memberships = {m.group_id: m for m in user.group_memberships.filter(group_id__in=ids).exclude(status=MembershipStatus.LEFT)}

    cards, invitations, owing = [], [], []
    for g in groups:
        total = funded.get(g.pk, Decimal("0.00"))
        percent = min(total / g.target_amount * 100, Decimal("100")) if g.target_amount else Decimal("0")
        m = memberships.get(g.pk)
        outstanding = max(m.contribution_share - mine.get(g.pk, Decimal("0.00")), Decimal("0.00")) if m else Decimal("0.00")
        card = {"group": g, "funded": total, "percent": round(percent, 1), "my_outstanding": outstanding,
                "is_admin": g.admin_id == user.pk, "membership": m}
        if m and m.status == MembershipStatus.INVITED and g.admin_id != user.pk:
            invitations.append(card)
            continue
        cards.append(card)
        if g.is_open_for_contributions and m and m.status == MembershipStatus.JOINED and outstanding > 0:
            owing.append(card)
    active = [c for c in cards if c["group"].status in (GroupStatus.OPEN, GroupStatus.OVERDUE, GroupStatus.FUNDED)]
    closed = [c for c in cards if c["group"].status in (GroupStatus.PAID_OUT, GroupStatus.CANCELLED)]
    stats = {
        "active": len(active),
        "owing_total": sum((c["my_outstanding"] for c in owing), Decimal("0.00")),
        "contributed": Contribution.objects.filter(member=user, status="paid").aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
    }
    return render(request, "dashboard.html", {
        "active": active, "closed": closed, "invitations": invitations, "owing": owing, "stats": stats,
        "recent": Notification.objects.filter(user=user)[:5],
    })


# --- groups ----------------------------------------------------------------------------------------

def _read_member_rows(request):
    """Repeated (identifier, custom share) inputs from the create form."""
    identifiers = request.POST.getlist("member_identifier")
    shares = request.POST.getlist("member_share")
    rows, problems = [], []
    for index, raw in enumerate(identifiers):
        raw = raw.strip()
        if not raw:
            continue
        user = group_services.find_user(raw)
        if user is None:
            problems.append(f"No SplitStay account found for “{raw}”. They need to register first.")
            continue
        share = None
        share_raw = (shares[index] if index < len(shares) else "").strip().replace(",", "")
        if share_raw:
            try:
                share = Decimal(share_raw)
                if share <= 0:
                    raise ValueError
            except (ValueError, ArithmeticError):
                problems.append(f"The custom share for “{raw}” isn't a valid amount.")
                continue
        rows.append((user, share, raw))
    return rows, problems


@login_required
def group_new(request):
    form = GroupForm(request.POST or None, initial={"payout_type": "bank_transfer", "purpose": "rent"})
    member_rows = []
    if request.method == "POST":
        member_rows = [{"identifier": i, "share": s} for i, s in zip(request.POST.getlist("member_identifier"), request.POST.getlist("member_share"))]
        parsed, problems = _read_member_rows(request)
        if form.is_valid() and not problems:
            fields = form.service_fields()
            if fields["payout_type"] == PayoutType.BILL_PAYMENT:
                try:
                    info = bill_services.validate_meter(fields["bill_service_id"], fields["bill_customer_id"], fields["bill_variation"])
                    if not info.valid:
                        form.add_error("bill_customer_id", f"The biller couldn't find that meter ({info.message or 'not found'}).")
                except BillProviderUnavailable:
                    pass  # can't reach the biller right now; the payout step validates again
            if not form.errors:
                try:
                    group = group_services.create_group(
                        admin=request.user, members=[(u, s) for u, s, _ in parsed], **fields
                    )
                except ValidationError as exc:
                    flash_errors(request, exc)
                else:
                    messages.success(request, f"“{group.name}” is ready. Invitations have been sent.")
                    return redirect("web:group_detail", pk=group.pk)
        for problem in problems:
            messages.error(request, problem)
    from .banks import BANKS  # noqa: F401

    return render(request, "groups/form.html", {
        "form": form, "member_rows": member_rows, "editing": None,
        "fee": _fee_policy(),
    })


def _fee_policy() -> dict:
    return {
        "type": settings.SERVICE_FEE_TYPE, "flat": settings.SERVICE_FEE_FLAT, "percent": settings.SERVICE_FEE_PERCENT,
    }


@login_required
def group_edit(request, pk):
    group = admin_only_group(request, pk)
    if not group.is_open_for_contributions:
        messages.error(request, "A closed group can no longer be edited.")
        return redirect("web:group_detail", pk=pk)
    initial = {
        "name": group.name, "description": group.description, "purpose": group.purpose,
        "target_amount": group.target_amount, "due_date": group.due_date, "is_recurring": group.is_recurring,
        "recurrence_interval": group.recurrence_interval or "", "allow_partial_payout": group.allow_partial_payout,
        "payout_type": group.payout_type, "bill_service_id": group.bill_service_id,
        "bill_variation": group.bill_variation or "prepaid", "bill_customer_id": group.bill_customer_id,
        "recipient_bank_code": group.recipient_bank_code, "recipient_account_name": group.recipient_account_name,
    }
    form = GroupForm(request.POST or None, initial=initial, editing=group)
    if request.method == "POST" and form.is_valid():
        try:
            group_services.update_group(group, **form.service_fields())
        except ValidationError as exc:
            flash_errors(request, exc)
        else:
            messages.success(request, "Group updated.")
            return redirect("web:group_detail", pk=pk)
    return render(request, "groups/form.html", {"form": form, "editing": group, "member_rows": [], "fee": _fee_policy()})


@login_required
def group_detail(request, pk):
    group = visible_group(request, pk)
    ctx = group_page_context(request, group, initial=True)
    return render(request, "groups/detail.html", ctx)


@login_required
@require_GET
def group_live(request, pk):
    """Polled by the group page. Returns out-of-band panels so the pot, members and ledger update in place."""
    group = member_only_group(request, pk)
    ctx = group_page_context(request, group, initial=False)
    ctx["oob"] = True
    return render(request, "groups/_live.html", ctx)


@login_required
def group_ledger(request, pk):
    group = member_only_group(request, pk)
    entries = ledger.group_entries(group)
    page = Paginator(entries, 25).get_page(request.GET.get("page"))
    return render(request, "groups/ledger.html", {
        "group": group, "page": page, "rows": ledger.member_rows(group), "summary": ledger.group_summary(group),
        "is_admin": group.admin_id == request.user.pk, "my_entries": ledger.group_entries(group, user=request.user),
    })


@login_required
@require_POST
def group_invite(request, pk):
    group = admin_only_group(request, pk)
    form = InviteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter an email address or phone number.")
        return redirect("web:group_detail", pk=pk)
    user = group_services.find_user(form.cleaned_data["identifier"])
    if user is None:
        messages.error(request, "No SplitStay account matches that. They need to register first, then you can invite them.")
        return redirect("web:group_detail", pk=pk)
    try:
        membership = group_services.add_member(group, user, form.cleaned_data.get("contribution_share"))
    except ValidationError as exc:
        flash_errors(request, exc)
    else:
        messages.success(request, f"{user.display_name} was invited. Shares were rebalanced.")
    return redirect("web:group_detail", pk=pk)


@login_required
@require_POST
def group_member_remove(request, pk, user_id):
    group = admin_only_group(request, pk)
    member = get_object_or_404(group.memberships.exclude(status=MembershipStatus.LEFT), user_id=user_id).user
    try:
        group_services.remove_member(group, member)
    except ValidationError as exc:
        flash_errors(request, exc)
    else:
        messages.success(request, f"{member.display_name} was removed and shares were rebalanced.")
    return redirect("web:group_detail", pk=pk)


@login_required
@require_POST
def group_member_share(request, pk, user_id):
    group = admin_only_group(request, pk)
    member = get_object_or_404(group.memberships.exclude(status=MembershipStatus.LEFT), user_id=user_id).user
    raw = request.POST.get("contribution_share", "").strip().replace(",", "")
    try:
        share = Decimal(raw) if raw else None
        group_services.set_member_share(group, member, share)
    except (ValueError, ArithmeticError):
        messages.error(request, "Enter a valid amount, or leave it empty to split equally.")
    except ValidationError as exc:
        flash_errors(request, exc)
    else:
        messages.success(request, f"{member.display_name}'s share was updated.")
    return redirect("web:group_detail", pk=pk)


@login_required
@require_POST
def group_accept(request, pk):
    group = visible_group(request, pk)
    try:
        group_services.accept_invitation(group, request.user)
    except ValidationError as exc:
        flash_errors(request, exc)
    else:
        messages.success(request, f"You joined “{group.name}”.")
    return redirect("web:group_detail", pk=pk)


@login_required
@require_POST
def group_decline(request, pk):
    group = visible_group(request, pk)
    try:
        group_services.leave_group(group, request.user)
    except ValidationError as exc:
        flash_errors(request, exc)
        return redirect("web:group_detail", pk=pk)
    messages.success(request, "You left the group.")
    return redirect("web:dashboard")


@login_required
@require_POST
def group_cancel(request, pk):
    group = admin_only_group(request, pk)
    try:
        group_services.cancel_group(group)
    except ValidationError as exc:
        flash_errors(request, exc)
    else:
        messages.success(request, "The group was cancelled.")
    return redirect("web:group_detail", pk=pk)


@login_required
@require_POST
def group_payout(request, pk):
    """Admin: pay out now (partial) or retry a failed payout."""
    group = admin_only_group(request, pk)
    try:
        record = payout_services.get_payout_record(group)
        if record is not None and record.status == "failed":
            payout_services.retry_payout(group)
            messages.success(request, "Retrying the payment now.")
        else:
            payout_services.request_payout(group, triggered_by=request.user, partial=True)
            messages.success(request, "Payout started. You'll be notified when it completes.")
    except ValidationError as exc:
        flash_errors(request, exc)
    return redirect("web:group_detail", pk=pk)


# --- paying ----------------------------------------------------------------------------------------------

@login_required
@require_POST
def group_pay(request, pk):
    group = visible_group(request, pk)
    try:
        contribution = contribution_services.initiate_contribution(group, request.user)
        url = payment_services.start_checkout(contribution)
    except ValidationError as exc:
        flash_errors(request, exc)
        return redirect("web:group_detail", pk=pk)
    except GatewayError:
        messages.error(request, "The payment gateway is unavailable right now. Nothing was charged; try again shortly.")
        return redirect("web:group_detail", pk=pk)
    return redirect(url)


@login_required
def payment_return(request):
    """Where the gateway sends the customer back. We verify with the gateway instead of trusting the URL."""
    reference = request.GET.get("reference") or request.GET.get("trxref") or ""
    contribution = get_object_or_404(Contribution, reference=reference, member=request.user)
    payment_services.verify_and_confirm(contribution)
    return redirect("web:contribution_confirmation", reference=reference)


@login_required
def contribution_confirmation(request, reference):
    contribution = get_object_or_404(Contribution.objects.select_related("group"), reference=reference, member=request.user)
    if contribution.status == ContributionStatus.PENDING:
        # The customer may return before the webhook lands; ask the gateway once more.
        contribution = payment_services.verify_and_confirm(contribution)
    ctx = {"contribution": contribution, "group": contribution.group}
    if is_htmx(request):
        return render(request, "payments/_confirmation_card.html", ctx)
    return render(request, "payments/confirmation.html", ctx)


@login_required
def mock_checkout(request, reference):
    """Sandbox stand-in for the gateway's hosted page. Only exists when PAYMENT_GATEWAY=mock."""
    if settings.PAYMENT_GATEWAY != "mock":
        raise Http404
    contribution = get_object_or_404(Contribution.objects.select_related("group"), reference=reference, member=request.user)
    if request.method == "POST":
        if contribution.status == ContributionStatus.PENDING:
            if request.POST.get("outcome") == "decline":
                payment_services.fail_contribution(reference, "Declined at checkout")
            else:
                payment_services.confirm_contribution(reference, paid_amount=contribution.amount, gateway_reference=f"mock-{reference}")
        return redirect("web:contribution_confirmation", reference=reference)
    return render(request, "payments/mock_checkout.html", {"contribution": contribution, "group": contribution.group})


# --- receipt ----------------------------------------------------------------------------------------------------------

@login_required
def group_receipt(request, pk):
    group = member_only_group(request, pk)
    record = payout_services.get_payout_record(group)
    if record is None:
        raise Http404
    paid = group.contributions.filter(status="paid").select_related("member", "member__profile").order_by("paid_at")
    ctx = {
        "group": group, "record": record, "is_bill": group.payout_type == PayoutType.BILL_PAYMENT,
        "contributions": paid, "fees": record.fees.all(), "is_admin": group.admin_id == request.user.pk,
    }
    if is_htmx(request):
        return render(request, "groups/_receipt_body.html", ctx)
    return render(request, "groups/receipt.html", ctx)


# --- notifications -------------------------------------------------------------------------------------------------------

@login_required
def notifications(request):
    page = Paginator(Notification.objects.filter(user=request.user).select_related("group"), 20).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {"page": page})


@login_required
def notification_open(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification_services.mark_read(request.user, [notification.pk])
    if notification.group_id and selectors.groups_visible_to(request.user).filter(pk=notification.group_id).exists():
        return redirect("web:group_detail", pk=notification.group_id)
    return redirect("web:notifications")


@login_required
@require_POST
def notifications_read_all(request):
    notification_services.mark_read(request.user)
    if is_htmx(request):
        return render(request, "notifications/_bell.html", {
            "oob": True, "unread_count": 0, "bell_notifications": list(Notification.objects.filter(user=request.user)[:6]),
        })
    return redirect(request.META.get("HTTP_REFERER") or reverse("web:notifications"))


@login_required
def notifications_bell(request):
    return render(request, "notifications/_bell.html", {
        "oob": True,
        "unread_count": notification_services.unread_count(request.user),
        "bell_notifications": list(Notification.objects.filter(user=request.user)[:6]),
    })


# --- account settings -------------------------------------------------------------------------------------------------------

@login_required
def account_settings(request):
    user = request.user
    account = BankAccount.objects.filter(user=user).first()
    profile_form = ProfileForm(initial={"full_name": user.profile.full_name, "phone_number": user.profile.phone_number or ""}, user=user)
    bank_form = BankAccountForm(initial={"bank_code": account.bank_code, "account_name": account.account_name} if account else None)
    if request.method == "POST":
        which = request.POST.get("form")
        if which == "profile":
            profile_form = ProfileForm(request.POST, user=user)
            if profile_form.is_valid():
                user.profile.full_name = profile_form.cleaned_data["full_name"]
                user.profile.phone_number = profile_form.cleaned_data["phone_number"]
                user.profile.save()
                messages.success(request, "Profile saved.")
                return redirect("web:settings")
        elif which == "bank":
            bank_form = BankAccountForm(request.POST)
            if bank_form.is_valid():
                bank_form.save(user)
                messages.success(request, "Bank account saved.")
                return redirect("web:settings")
        elif which == "bank_remove":
            BankAccount.objects.filter(user=user).delete()
            messages.success(request, "Bank account removed.")
            return redirect("web:settings")
    return render(request, "account/settings.html", {"profile_form": profile_form, "bank_form": bank_form, "account": account})


# --- htmx helper: validate a meter while creating a group ------------------------------------------------------------------------------

@login_required
@require_POST
def validate_meter(request):
    service_id = request.POST.get("bill_service_id", "")
    customer_id = request.POST.get("bill_customer_id", "").strip()
    variation = request.POST.get("bill_variation") or "prepaid"
    if not service_id or not customer_id:
        return HttpResponse('<p class="hint">Choose the company and enter the meter number to check it.</p>')
    try:
        info = bill_services.validate_meter(service_id, customer_id, variation)
    except BillProviderUnavailable:
        return render(request, "groups/_meter_result.html", {"unavailable": True})
    return render(request, "groups/_meter_result.html", {"info": info})
