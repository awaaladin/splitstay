from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.contributions.models import Contribution
from apps.groups.models import ContributionGroup, GroupStatus
from apps.testing import make_group, make_user, pay


class PublicPageTests(TestCase):
    def test_public_pages_render(self):
        for name in ("web:landing", "web:login", "web:register"):
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 200, name)
        self.assertContains(self.client.get(reverse("web:landing")), "Shared costs")

    def test_dark_mode_and_theme_toggle_present(self):
        html = self.client.get(reverse("web:landing")).content.decode()
        self.assertIn("themeToggle()", html)
        self.assertIn("cp-theme", html)  # persisted choice, applied before first paint

    def test_private_pages_redirect_to_login(self):
        for name in ("web:dashboard", "web:group_new", "web:notifications", "web:settings"):
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 302, name)
            self.assertIn("/login/", res["Location"])

    def test_register_and_login_flow(self):
        res = self.client.post(reverse("web:register"), {
            "full_name": "Ada Obi", "email": "ada@example.com", "phone_number": "08031234567", "password": "Str0ng-pass!",
        })
        self.assertRedirects(res, reverse("web:dashboard"))
        self.client.post(reverse("web:logout"))
        res = self.client.post(reverse("web:login"), {"identifier": "08031234567", "password": "Str0ng-pass!"})
        self.assertRedirects(res, reverse("web:dashboard"))

    def test_bad_login_shows_error(self):
        res = self.client.post(reverse("web:login"), {"identifier": "x@y.com", "password": "nope"})
        self.assertContains(res, "don&#x27;t match")


class SeededPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def login(self, handle="ada"):
        self.client.login(username=f"{handle}@demo.splitstay.test", password="demo12345")

    def test_seed_creates_three_groups_with_expected_states(self):
        names = set(ContributionGroup.objects.filter(cycle_number=1).values_list("name", flat=True))
        self.assertEqual(names, {"Flat 4B Rent", "Lekki Flat Electricity", "Mama's Monthly Upkeep"})
        nepa = ContributionGroup.objects.get(name="Lekki Flat Electricity")
        self.assertEqual(nepa.status, GroupStatus.PAID_OUT)
        self.assertTrue(nepa.bill_payment.token)
        self.assertEqual(ContributionGroup.objects.get(name="Flat 4B Rent").status, GroupStatus.OPEN)

    def test_seed_is_idempotent_and_resettable(self):
        call_command("seed_demo", verbosity=0)
        self.assertEqual(ContributionGroup.objects.count(), 3)
        call_command("seed_demo", "--reset", verbosity=0)
        self.assertEqual(ContributionGroup.objects.count(), 3)

    def test_dashboard_shows_real_data(self):
        self.login("ibrahim")  # hasn't paid this month's rent yet
        res = self.client.get(reverse("web:dashboard"))
        self.assertContains(res, "Flat 4B Rent")
        self.assertContains(res, "Waiting on you")
        self.login("tunde")
        self.assertContains(self.client.get(reverse("web:dashboard")), "Lekki Flat Electricity")

    def test_invited_user_sees_invitation_and_limited_group_page(self):
        self.login("ngozi")
        res = self.client.get(reverse("web:dashboard"))
        self.assertContains(res, "Invitations")
        family = ContributionGroup.objects.get(name="Mama's Monthly Upkeep")
        page = self.client.get(reverse("web:group_detail", args=[family.pk]))
        self.assertContains(page, "invited you")
        self.assertNotContains(page, 'id="ledger"')  # history is for joined members only
        self.assertEqual(self.client.get(reverse("web:group_ledger", args=[family.pk])).status_code, 404)

    def test_every_member_page_renders(self):
        self.login("chioma")
        for group in ContributionGroup.objects.filter(memberships__user__email__startswith="chioma"):
            for name in ("web:group_detail", "web:group_live", "web:group_ledger"):
                res = self.client.get(reverse(name, args=[group.pk]))
                self.assertEqual(res.status_code, 200, f"{name} {group}")
        for name in ("web:notifications", "web:settings", "web:notifications_bell"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_group_page_has_pot_members_and_ledger(self):
        self.login("ada")
        rent = ContributionGroup.objects.get(name="Flat 4B Rent")
        html = self.client.get(reverse("web:group_detail", args=[rent.pk])).content.decode()
        for marker in ('id="pot"', 'data-pot-liquid', 'id="members"', 'id="ledger"', 'id="actions"', "group_live" if False else "/live/"):
            self.assertIn(marker, html)
        # first render starts empty so the fill can animate after the boot screen
        self.assertIn("data-translate=", html)

    def test_live_partial_returns_out_of_band_panels_at_final_level(self):
        self.login("ada")
        rent = ContributionGroup.objects.get(name="Flat 4B Rent")
        html = self.client.get(reverse("web:group_live", args=[rent.pk])).content.decode()
        self.assertEqual(html.count('hx-swap-oob="true"'), 6)  # badge, header actions, pot, actions, members, ledger
        self.assertIn("translateY(", html)
        self.assertNotIn("data-translate", html)

    def test_live_panels_reflect_a_new_contribution_immediately(self):
        self.login("ada")
        rent = ContributionGroup.objects.get(name="Flat 4B Rent")
        before = self.client.get(reverse("web:group_live", args=[rent.pk])).content.decode()
        ibrahim = ContributionGroup.objects.get(pk=rent.pk).memberships.get(user__email__startswith="ibrahim").user
        pay(rent, ibrahim)
        after = self.client.get(reverse("web:group_live", args=[rent.pk])).content.decode()
        self.assertNotEqual(before, after)
        self.assertIn("Ibrahim Musa", after)
        self.assertIn("Contribution", after)

    def test_outsider_gets_404_for_group(self):
        outsider = make_user("Outsider", password="pass12345!")
        self.client.login(username=outsider.email, password="pass12345!")
        rent = ContributionGroup.objects.get(name="Flat 4B Rent")
        for name in ("web:group_detail", "web:group_live", "web:group_ledger"):
            self.assertEqual(self.client.get(reverse(name, args=[rent.pk])).status_code, 404)

    def test_receipt_renders_token_fee_and_contributions(self):
        self.login("tunde")
        nepa = ContributionGroup.objects.get(name="Lekki Flat Electricity")
        html = self.client.get(reverse("web:group_receipt", args=[nepa.pk])).content.decode()
        self.assertIn(nepa.bill_payment.token, html)
        self.assertIn("₦150.00", html)  # the fee is an explicit line
        self.assertIn("₦29,850.00", html)
        self.assertIn("receipt-line", html)

    def test_receipt_404_before_payout_exists(self):
        self.login("ada")
        rent = ContributionGroup.objects.get(name="Flat 4B Rent")
        self.assertEqual(self.client.get(reverse("web:group_receipt", args=[rent.pk])).status_code, 404)


class WebFlowTests(TestCase):
    def setUp(self):
        self.admin = make_user("Admin", password="pass12345!")
        self.friend = make_user("Friend", email="friend@example.com", password="pass12345!")
        self.client.login(username=self.admin.email, password="pass12345!")

    def create_payload(self, **overrides):
        data = {
            "name": "Office rent", "description": "", "purpose": "rent", "target_amount": "100000",
            "due_date": (date.today() + timedelta(days=20)).isoformat(), "payout_type": "bank_transfer",
            "recipient_bank_code": "058", "recipient_account_number": "0123456789", "recipient_account_name": "Landlord Ltd",
            "member_identifier": ["friend@example.com", ""], "member_share": ["", ""],
        }
        data.update(overrides)
        return data

    def test_create_group_with_member_via_form(self):
        res = self.client.post(reverse("web:group_new"), self.create_payload())
        group = ContributionGroup.objects.get(name="Office rent")
        self.assertRedirects(res, reverse("web:group_detail", args=[group.pk]))
        self.assertEqual(group.memberships.count(), 2)
        self.assertEqual(sum(m.contribution_share for m in group.memberships.all()), Decimal("100000.00"))
        self.assertEqual(group.recipient_account_number, "0123456789")

    def test_create_form_rejects_unknown_member_and_past_date(self):
        res = self.client.post(reverse("web:group_new"), self.create_payload(member_identifier=["ghost@example.com"], member_share=[""]))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(ContributionGroup.objects.exists())
        res = self.client.post(reverse("web:group_new"), self.create_payload(due_date="2020-01-01"))
        self.assertContains(res, "can&#x27;t be in the past")

    def test_create_bill_group_requires_biller_and_meter(self):
        res = self.client.post(reverse("web:group_new"), self.create_payload(
            payout_type="bill_payment", purpose="electricity", member_identifier=[], member_share=[]))
        self.assertContains(res, "Choose the electricity company")
        res = self.client.post(reverse("web:group_new"), self.create_payload(
            payout_type="bill_payment", purpose="electricity", bill_service_id="ikeja-electric",
            bill_customer_id="45012345678", bill_variation="prepaid", member_identifier=[], member_share=[]))
        group = ContributionGroup.objects.get(name="Office rent")
        self.assertEqual(group.payout_type, "bill_payment")

    def test_full_pay_flow_through_mock_checkout_to_confirmation_and_receipt(self):
        self.client.post(reverse("web:group_new"), self.create_payload(target_amount="60000"))
        group = ContributionGroup.objects.get(name="Office rent")
        self.client.post(reverse("web:group_accept", args=[group.pk]))  # admin is already joined; harmless
        friend_client = self.client_class()
        friend_client.login(username=self.friend.email, password="pass12345!")
        friend_client.post(reverse("web:group_accept", args=[group.pk]))

        with self.captureOnCommitCallbacks(execute=True):
            for client in (self.client, friend_client):
                res = client.post(reverse("web:group_pay", args=[group.pk]))
                self.assertEqual(res.status_code, 302)
                self.assertIn("/pay/mock/", res["Location"])
                checkout = client.get(res["Location"])
                self.assertContains(checkout, "Sandbox checkout")
                done = client.post(res["Location"], {"outcome": "success"})
                confirm_url = done["Location"]
                page = client.get(confirm_url)
                self.assertContains(page, "Payment confirmed")
                self.assertContains(page, "confirm-check")  # the self-drawing tick

        group.refresh_from_db()
        self.assertEqual(group.status, GroupStatus.PAID_OUT)
        receipt = self.client.get(reverse("web:group_receipt", args=[group.pk]))
        self.assertContains(receipt, "Paid")
        self.assertContains(receipt, "Landlord Ltd")
        self.assertContains(receipt, "₦150.00")

    def test_declined_payment_shows_failure_and_adds_nothing(self):
        self.client.post(reverse("web:group_new"), self.create_payload(member_identifier=[], member_share=[]))
        group = ContributionGroup.objects.get(name="Office rent")
        res = self.client.post(reverse("web:group_pay", args=[group.pk]))
        done = self.client.post(res["Location"], {"outcome": "decline"})
        self.assertContains(self.client.get(done["Location"]), "go through")
        self.assertEqual(group.total_funded, Decimal("0.00"))

    def test_confirmation_page_polls_while_pending(self):
        group = make_group(self.admin, target="30000", members=0)
        from apps.contributions.services import initiate_contribution

        contribution = initiate_contribution(group, self.admin)
        page = self.client.get(reverse("web:contribution_confirmation", args=[contribution.reference]))
        self.assertContains(page, "Confirming your payment")
        self.assertContains(page, 'hx-trigger="every 3s"')

    def test_cannot_view_someone_elses_confirmation(self):
        group = make_group(self.admin, target="30000", members=1)
        other = group.memberships.exclude(user=self.admin).first().user
        contribution = pay(group, other)
        res = self.client.get(reverse("web:contribution_confirmation", args=[contribution.reference]))
        self.assertEqual(res.status_code, 404)

    def test_admin_actions_are_admin_only(self):
        group = make_group(self.admin, target="90000", members=2)
        member = group.memberships.exclude(user=self.admin).first().user
        self.client.logout()
        self.client.login(username=member.email, password="pass12345!")
        self.assertEqual(self.client.post(reverse("web:group_cancel", args=[group.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("web:group_payout", args=[group.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("web:group_edit", args=[group.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("web:group_invite", args=[group.pk]), {"identifier": "x@y.com"}).status_code, 404)

    def test_notification_open_marks_read_and_bell_updates(self):
        group = make_group(self.admin, target="30000", members=1)
        other = group.memberships.exclude(user=self.admin).first().user
        pay(group, other)
        from apps.notifications.models import Notification

        note = Notification.objects.filter(user=self.admin, kind="contribution").first()
        res = self.client.get(reverse("web:notification_open", args=[note.pk]))
        self.assertRedirects(res, reverse("web:group_detail", args=[group.pk]), fetch_redirect_response=False)
        note.refresh_from_db()
        self.assertIsNotNone(note.read_at)
        bell = self.client.get(reverse("web:notifications_bell"))
        self.assertContains(bell, 'hx-swap-oob="true"')

    def test_settings_saves_encrypted_bank_account(self):
        res = self.client.post(reverse("web:settings"), {
            "form": "bank", "bank_code": "058", "account_number": "0123456789", "account_name": "Admin User"})
        self.assertRedirects(res, reverse("web:settings"))
        page = self.client.get(reverse("web:settings"))
        self.assertContains(page, "6789")
        self.assertNotContains(page, "0123456789")

    def test_validate_meter_partial(self):
        res = self.client.post(reverse("web:validate_meter"), {
            "bill_service_id": "ikeja-electric", "bill_customer_id": "45012345678", "bill_variation": "prepaid"})
        self.assertContains(res, "DEMO CUSTOMER")
        res = self.client.post(reverse("web:validate_meter"), {
            "bill_service_id": "ikeja-electric", "bill_customer_id": "45012349999", "bill_variation": "prepaid"})
        self.assertContains(res, "Meter not found")
