"""Template helpers: outlined SVG icons (Lucide paths, one consistent stroke), money and status formatting."""
from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Lucide outline icons, 24x24 viewBox. Rendered with a uniform 1.5 stroke.
ICONS = {
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "menu": '<path d="M4 12h16"/><path d="M4 6h16"/><path d="M4 18h16"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "wallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "receipt": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "building": '<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>',
    "repeat": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "printer": '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
    "landmark": '<path d="M3 22h18"/><path d="M6 18v-7"/><path d="M10 18v-7"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M12 2 20 7H4z"/>',
    "tv": '<rect width="20" height="15" x="2" y="7" rx="2" ry="2"/><path d="m17 2-5 5-5-5"/>',
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "pencil": '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
    "banknote": '<rect width="20" height="12" x="2" y="6" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
    "list": '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "mail": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
}


@register.simple_tag
def icon(name, size=20, css=""):
    body = ICONS.get(name, "")
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" '
        'class="shrink-0 {}" aria-hidden="true">{}</svg>',
        size, size, css, mark_safe(body),
    )


PURPOSE_ICONS = {
    "rent": "building", "electricity": "zap", "subscription": "repeat", "family_upkeep": "users", "custom": "layers",
}


@register.simple_tag
def purpose_icon(purpose, size=20, css=""):
    return icon(PURPOSE_ICONS.get(purpose, "layers"), size, css)


@register.filter
def naira(value, places=2):
    """₦1,234.50. Accepts Decimal/int/str; blank for None."""
    if value in (None, ""):
        return ""
    value = Decimal(value)
    places = int(places)
    return f"₦{value:,.{places}f}"


@register.filter
def naira_short(value):
    """₦90,000 (no kobo when whole)."""
    if value in (None, ""):
        return ""
    value = Decimal(value)
    return f"₦{value:,.0f}" if value == value.to_integral_value() else f"₦{value:,.2f}"


GROUP_BADGES = {
    "open": ("badge-primary", "Open"),
    "funded": ("badge-ok", "Funded"),
    "paid_out": ("badge-ok", "Paid out"),
    "cancelled": ("badge-neutral", "Cancelled"),
    "overdue": ("badge-warn", "Overdue"),
}
PAYOUT_BADGES = {
    "pending": ("badge-neutral", "Pending"),
    "processing": ("badge-primary", "Processing"),
    "completed": ("badge-ok", "Completed"),
    "failed": ("badge-danger", "Failed"),
}
CONTRIBUTION_BADGES = {
    "paid": ("badge-ok", "Paid"),
    "pending": ("badge-neutral", "Pending"),
    "failed": ("badge-danger", "Failed"),
}
MEMBER_BADGES = {
    "paid": ("badge-ok", "Paid"),
    "partial": ("badge-warn", "Part-paid"),
    "unpaid": ("badge-neutral", "Not yet paid"),
    "invited": ("badge-neutral", "Invited"),
}
_BADGES = {
    "group": GROUP_BADGES, "payout": PAYOUT_BADGES, "contribution": CONTRIBUTION_BADGES, "member": MEMBER_BADGES,
}


@register.simple_tag
def status_badge(kind, value):
    css, label = _BADGES[kind].get(value, ("badge-neutral", str(value).replace("_", " ").title()))
    return format_html('<span class="{}"><span class="dot"></span>{}</span>', css, label)


@register.filter
def initials(user):
    return user.initials


@register.filter
def as_input(bound_field, extra=""):
    """Render a form field with the design system's input classes."""
    from django import forms

    widget = bound_field.field.widget
    if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
        return bound_field
    kind = "select" if isinstance(widget, forms.Select) else "textarea" if isinstance(widget, forms.Textarea) else "input"
    attrs = {"class": f"{kind} {extra}".strip()}
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    return bound_field.as_widget(attrs=attrs)


@register.filter
def mask_meter(value):
    value = str(value or "")
    return f"{'•' * max(len(value) - 4, 0)}{value[-4:]}"


@register.simple_tag
def logo_mark(uid="m", size=32):
    """The SplitStay mark: a vessel filling with liquid. `uid` keeps clipPath ids unique per instance."""
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 32 32" fill="none" aria-hidden="true">'
        '<defs><clipPath id="cp-clip-{uid}"><rect x="4" y="4" width="24" height="24" rx="7"/></clipPath></defs>'
        '<g clip-path="url(#cp-clip-{uid})"><g class="mark-fill">'
        '<rect x="4" y="4" width="24" height="24" fill="currentColor" opacity="0.92"/>'
        '<path class="mark-wave" d="M-8 4 q4 -3 8 0 t8 0 t8 0 t8 0 t8 0 t8 0 t8 0 t8 0 V8 H-8Z" fill="currentColor"/>'
        '</g></g>'
        '<rect class="mark-outline" pathLength="1" x="4" y="4" width="24" height="24" rx="7" stroke="currentColor" stroke-width="2"/>'
        '</svg>',
        size=size, uid=uid,
    )
