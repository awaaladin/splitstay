"""Email: welcome, payment and payout notices, forgot-password. SMTP is never contacted (Django's test mailbox)."""
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.notifications import mailer
from apps.testing import make_group, make_user, pay


class MailerTests(TestCase):
    def test_a_broken_mail_server_never_raises(self):
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp down")):
            self.assertFalse(mailer.send_email("a@example.com", "Hi", "notice", {"headline": "x", "body": "y", "name": "A"}))

    def test_no_recipient_sends_nothing(self):
        self.assertFalse(mailer.send_email("", "Hi", "notice"))
        self.assertEqual(len(mail.outbox), 0)

    def test_user_text_is_escaped_and_subject_has_no_newlines(self):
        mailer.send_email("a@example.com", "Hi\nBcc: x@y.z", "notice", {"headline": "<script>x</script>", "body": "b", "name": "<b>N</b>"})
        message = mail.outbox[0]
        self.assertNotIn("\n", message.subject)
        self.assertNotIn("<script>", message.alternatives[0][0])
        self.assertIn("&lt;script&gt;", message.alternatives[0][0])

    def test_nothing_is_sent_when_the_transaction_rolls_back(self):
        from django.db import transaction

        try:
            with transaction.atomic():
                mailer.send_after_commit("a@example.com", "Hi", "notice", {"headline": "x", "body": "y", "name": "A"})
                raise RuntimeError("rolled back")
        except RuntimeError:
            pass
        self.assertEqual(len(mail.outbox), 0)


class EventEmailTests(TestCase):
    def test_signup_sends_a_welcome_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            make_user("Ada", email="ada@example.com")
        self.assertEqual([m.to for m in mail.outbox], [["ada@example.com"]])
        self.assertIn("Welcome", mail.outbox[0].subject)

    def test_payer_gets_a_receipt_but_other_members_are_not_emailed_for_it(self):
        group = make_group(target="90000", members=2)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            pay(group, group.admin)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertEqual(recipients, [group.admin.email])
        self.assertIn("Payment received", mail.outbox[0].subject)

    def test_funding_and_payout_notices_reach_everyone(self):
        group = make_group(target="90000", members=2)
        members = [m.user for m in group.memberships.filter(status="joined")] + [group.admin]
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            for user in {u.pk: u for u in members}.values():
                pay(group, user)
        funded = [m for m in mail.outbox if "fully funded" in m.subject]
        self.assertEqual(len(funded), len({u.pk for u in members}))


@override_settings(SITE_URL="https://splitpay.test")
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = make_user("Reset Me", email="reset@example.com", password="Old-pass-12345!")
        mail.outbox.clear()

    def _link(self):
        body = mail.outbox[-1].body
        return next(w for w in body.split() if w.startswith("https://splitpay.test/password-reset/"))

    def test_api_flow_changes_the_password_once(self):
        c = APIClient()
        r = c.post("/api/v1/auth/password-reset/", {"email": "reset@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        _, _, rest = self._link().partition("/password-reset/")
        uid, token = rest.strip("/").split("/")
        bad = c.post("/api/v1/auth/password-reset/confirm/", {"uid": uid, "token": token, "password": "123"}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = c.post("/api/v1/auth/password-reset/confirm/", {"uid": uid, "token": token, "password": "A-new-strong-pass-77!"}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("A-new-strong-pass-77!"))
        again = c.post("/api/v1/auth/password-reset/confirm/", {"uid": uid, "token": token, "password": "Another-strong-pass-88!"}, format="json")
        self.assertEqual(again.status_code, 400, "a reset link must work only once")

    def test_unknown_email_gets_the_same_answer_and_no_email(self):
        r = APIClient().post("/api/v1/auth/password-reset/", {"email": "nobody@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_website_flow(self):
        self.client.post("/password-reset/", {"email": "reset@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        path = self._link().replace("https://splitpay.test", "")
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        done = self.client.post(path, {"password": "A-new-strong-pass-77!", "confirm": "A-new-strong-pass-77!"})
        self.assertEqual(done.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password("A-new-strong-pass-77!"))

    def test_a_tampered_link_is_refused(self):
        self.client.post("/password-reset/", {"email": "reset@example.com"})
        path = self._link().replace("https://splitpay.test", "")
        self.assertEqual(self.client.get(path[:-2] + "xx/").status_code, 400)
