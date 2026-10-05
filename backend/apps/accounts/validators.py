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
