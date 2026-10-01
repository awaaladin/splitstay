"""Shared factories for tests and the seed command."""
import itertools
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.contributions.models import Contribution
from apps.groups import services as group_services
from apps.groups.models import MembershipStatus
from apps.payments import services as payment_services

User = get_user_model()
_counter = itertools.count(1)


def make_user(name: str = "", email: str | None = None, phone: str | None = None, password: str = "pass12345!"):
    n = next(_counter)
    email = email or f"user{n}@example.com"
    user = User.objects.create_user(email=email, password=password)
    user.profile.full_name = name or f"User {n}"
    user.profile.phone_number = phone
    user.profile.save()
    return user


def make_group(admin=None, *, target="90000", members=2, joined=True, **overrides):
    """A group with `members` extra people (all joined by default). Equal split unless overridden."""
    admin = admin or make_user("Admin")
    others = [make_user() for _ in range(members)]
    fields = dict(
        name="Flat 4 Rent", purpose="rent", target_amount=Decimal(target),
        due_date=date.today() + timedelta(days=10), payout_type="bank_transfer",
        recipient_bank_code="058", recipient_bank_name="GTBank", recipient_account_name="Mr Landlord",
        recipient_account_number="0123456789",
    )
    fields.update(overrides)
    group = group_services.create_group(admin=admin, members=[(u, None) for u in others], **fields)
    if joined:
        for m in group.memberships.filter(status=MembershipStatus.INVITED):
            group_services.accept_invitation(group, m.user)
    return group


def pay(group, user, amount=None, *, gateway_amount=None):
    """Run a member's contribution all the way to PAID via the same path a webhook uses."""
    from apps.contributions.services import initiate_contribution

    contribution = initiate_contribution(group, user, amount)
    payment_services.confirm_contribution(contribution.reference, paid_amount=gateway_amount or contribution.amount)
    return Contribution.objects.get(pk=contribution.pk)
