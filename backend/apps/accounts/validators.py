import re

from django.core.exceptions import ValidationError

# Mirrors the live checklist shown on the sign-up form.
RULES = [
    (r"[a-z]", "at least one lowercase letter"),
    (r"[A-Z]", "at least one uppercase letter"),
    (r"\d", "at least one number"),
    (r"[^A-Za-z0-9]", "at least one symbol"),
]


class PasswordComplexityValidator:
    def validate(self, password, user=None):
        missing = [label for pattern, label in RULES if not re.search(pattern, password)]
        if missing:
            raise ValidationError(
                "Your password needs " + ", ".join(missing) + ".",
                code="password_too_simple",
            )

    def get_help_text(self):
        return "Your password must contain upper and lowercase letters, a number and a symbol."


PHONE_HELP = "Enter a valid phone number, e.g. 0712 345 678."


def normalize_phone(value: str) -> str:
    """Kenyan numbers in any common format become +2547XXXXXXXX / +2541XXXXXXXX;
    other countries must be written with their + code. Raises ValidationError otherwise."""
    digits = re.sub(r"[\s\-().]", "", value or "")
    kenyan = re.fullmatch(r"(?:\+?254|0)?([17]\d{8})", digits)
    if kenyan:
        return f"+254{kenyan.group(1)}"
    if re.fullmatch(r"\+[1-9]\d{7,14}", digits):
        return digits
    raise ValidationError(PHONE_HELP, code="invalid_phone")
