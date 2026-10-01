import re


def normalize_phone(raw: str) -> str:
    """Normalise Nigerian numbers to E.164 (+234XXXXXXXXXX). Other numbers keep their digits."""
    if not raw:
        return ""
    digits = re.sub(r"[^\d+]", "", raw.strip())
    if digits.startswith("+"):
        return digits
    if digits.startswith("234"):
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+234" + digits[1:]
    if len(digits) == 10:
        return "+234" + digits
    return digits
