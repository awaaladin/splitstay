from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.web.models import ContactMessage
from apps.testing import make_user

PUBLIC = ("web:landing", "web:guide", "web:about", "web:pricing", "web:contact", "web:privacy", "web:terms")


class PublicPagesTests(TestCase):
    def test_every_public_page_renders_for_visitors(self):
        for name in PUBLIC:
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 200, name)

    def test_footer_links_to_every_page(self):
        html = self.client.get(reverse("web:landing")).content.decode()
        for name in ("web:guide", "web:pricing", "web:about", "web:contact", "web:privacy", "web:terms"):
            self.assertIn(f'href="{reverse(name)}"', html, name)

    def test_guide_covers_the_whole_journey(self):
        html = self.client.get(reverse("web:guide")).content.decode()
        for phrase in ("Create account", "New group", "Check this meter", "Join", "Pay ₦", "Payment confirmed",
                       "View receipt", "Retry payment", "Copy token", "Cancel group", "Is my money safe?"):
            self.assertIn(phrase, html, phrase)

    def test_landing_no_longer_embeds_the_full_guide_but_links_to_it(self):
        html = self.client.get(reverse("web:landing")).content.decode()
        self.assertNotIn('id="g-start"', html)
        self.assertIn(reverse("web:guide"), html)

    def test_signed_in_users_can_still_open_guide_and_landing_redirects(self):
        user = make_user("Reader", password="pass12345!")
        self.client.login(username=user.email, password="pass12345!")
        self.assertEqual(self.client.get(reverse("web:guide")).status_code, 200)
        self.assertEqual(self.client.get(reverse("web:landing")).status_code, 302)

    def test_fees_page_uses_live_settings(self):
        with override_settings(SERVICE_FEE_TYPE="flat", SERVICE_FEE_FLAT=200):
            html = self.client.get(reverse("web:pricing")).content.decode()
        self.assertIn("₦200", html)
        self.assertIn("₦29,800.00", html)  # 30,000 pool minus the 200 fee
        with override_settings(SERVICE_FEE_TYPE="percent", SERVICE_FEE_PERCENT=2, SERVICE_FEE_MIN=0, SERVICE_FEE_MAX=0):
            html = self.client.get(reverse("web:pricing")).content.decode()
        self.assertIn("2%", html)
        self.assertIn("₦29,400.00", html)


class ContactTests(TestCase):
    def setUp(self):
        cache.clear()

    def payload(self, **kw):
        data = {"name": "Ada", "email": "ada@example.com", "topic": "help", "message": "How do I add a member?", "reference": "", "website": ""}
        data.update(kw)
        return data

    def test_message_is_saved(self):
        res = self.client.post(reverse("web:contact"), self.payload())
        self.assertRedirects(res, reverse("web:contact"))
        message = ContactMessage.objects.get()
        self.assertEqual((message.email, message.topic), ("ada@example.com", "help"))

    def test_signed_in_form_is_prefilled_and_linked_to_user(self):
        user = make_user("Tolu", password="pass12345!")
        self.client.login(username=user.email, password="pass12345!")
        self.assertContains(self.client.get(reverse("web:contact")), user.email)
        self.client.post(reverse("web:contact"), self.payload(email=user.email))
        self.assertEqual(ContactMessage.objects.get().user, user)

    def test_honeypot_blocks_bots(self):
        self.client.post(reverse("web:contact"), self.payload(website="http://spam.example"))
        self.assertFalse(ContactMessage.objects.exists())

    def test_invalid_form_is_rejected(self):
        res = self.client.post(reverse("web:contact"), self.payload(email="not-an-email", message=""))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(ContactMessage.objects.exists())

    def test_rate_limited_after_five_messages(self):
        for _ in range(7):
            self.client.post(reverse("web:contact"), self.payload())
        self.assertEqual(ContactMessage.objects.count(), 5)
