"""Every email SplitPay sends goes through here.

Rules:
* An email problem (bad SMTP login, provider outage) can NEVER fail the request that triggered it:
  `send_email` logs and returns False instead of raising.
* Event emails go out only AFTER the database transaction commits, so a rolled-back payment never
  produces a "payment received" email.
* HTML is rendered with Django's autoescaping (group names and people's names are user input) and
  subjects have newlines stripped.
* Logs name the template and a masked address, never the full recipient, a code or a link.
"""
import logging
from html import unescape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

log = logging.getLogger(__name__)


def _mask(address: str) -> str:
    name, _, domain = (address or "").partition("@")
    return f"{name[:1]}***@{domain}"


def base_context() -> dict:
    return {
        "brand": "SplitPay",
        "site_url": settings.SITE_URL.rstrip("/"),
        "year": timezone.now().year,
        "support_email": settings.SUPPORT_EMAIL,
    }


def _plain_text(html: str) -> str:
    lines = (" ".join(line.split()) for line in unescape(strip_tags(html)).splitlines())
    return "\n".join(line for line in lines if line)


def send_email(to: str, subject: str, template: str, context: dict | None = None) -> bool:
    """Renders emails/<template>.html and sends it. Never raises."""
    if not to:
        return False
    try:
        html = render_to_string(f"emails/{template}.html", {**base_context(), **(context or {})})
        message = EmailMultiAlternatives(
            subject=" ".join(subject.split()),
            body=_plain_text(html),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        log.info("Sent the %s email to %s", template, _mask(to))
        return True
    except Exception:  # noqa: BLE001 - email trouble must never break the caller
        log.exception("Could not send the %s email to %s", template, _mask(to))
        return False


def send_after_commit(to: str, subject: str, template: str, context: dict | None = None) -> None:
    transaction.on_commit(lambda: send_email(to, subject, template, context))


def display_name(user) -> str:
    try:
        return user.display_name
    except Exception:  # noqa: BLE001
        return (user.email or "").split("@")[0]


def send_welcome(user) -> None:
    send_after_commit(user.email, "Welcome to SplitPay", "welcome", {"name": display_name(user)})
