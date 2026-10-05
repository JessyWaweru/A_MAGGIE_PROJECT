"""Six-digit email verification codes for sign-up.

Codes are short-lived, limited to a few guesses, rate-limited on resend, and
stored only as an HMAC so a database leak doesn't expose live codes.
"""

import hashlib
import hmac
import math
import secrets
from datetime import timedelta
from enum import Enum

from django.conf import settings
from django.utils import timezone

from .emails import send_verification_code_email
from .models import EmailVerificationCode

CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


class CodeCheck(Enum):
    OK = "ok"
    INVALID = "invalid"
    TOO_MANY_ATTEMPTS = "too_many_attempts"


def _hash(user, code: str) -> str:
    message = f"{user.pk}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def seconds_until_resend(user) -> int:
    record = EmailVerificationCode.objects.filter(user=user).first()
    if not record:
        return 0
    remaining = (record.created_at + RESEND_COOLDOWN - timezone.now()).total_seconds()
    return max(0, math.ceil(remaining))


def issue_code(user) -> bool:
    """Email a fresh code unless one was sent within the cooldown. Returns whether one was sent."""
    if seconds_until_resend(user):
        return False
    code = f"{secrets.randbelow(10**6):06d}"
    now = timezone.now()
    EmailVerificationCode.objects.update_or_create(
        user=user,
        defaults={"code_hash": _hash(user, code), "created_at": now, "expires_at": now + CODE_TTL, "attempts": 0},
    )
    send_verification_code_email(user, code, int(CODE_TTL.total_seconds() // 60))
    return True


def check_code(user, code: str) -> CodeCheck:
    record = EmailVerificationCode.objects.filter(user=user).first()
    if not record or record.expires_at <= timezone.now():
        return CodeCheck.INVALID
    if record.attempts >= MAX_ATTEMPTS:
        return CodeCheck.TOO_MANY_ATTEMPTS
    if not hmac.compare_digest(record.code_hash, _hash(user, code.strip())):
        record.attempts += 1
        record.save(update_fields=["attempts"])
        return CodeCheck.TOO_MANY_ATTEMPTS if record.attempts >= MAX_ATTEMPTS else CodeCheck.INVALID
    record.delete()
    return CodeCheck.OK
