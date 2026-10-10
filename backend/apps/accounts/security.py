"""Protection for account-changing actions: session revocation, re-checking the
current password, and the email-change confirmation and undo flow."""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from enum import Enum

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailChangeRequest

logger = logging.getLogger(__name__)

SESSION_VERSION_CLAIM = "sv"
MAX_PASSWORD_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
EMAIL_CODE_TTL = timedelta(minutes=10)
EMAIL_CODE_MAX_ATTEMPTS = 5
REVERT_WINDOW = timedelta(days=7)
REVERT_SALT = "accounts.email-change-revert"


def issue_refresh_token(user) -> RefreshToken:
    """A refresh token (and, through it, access tokens) stamped with the user's session version."""
    refresh = RefreshToken.for_user(user)
    refresh[SESSION_VERSION_CLAIM] = user.session_version
    return refresh


def token_is_current(token, user) -> bool:
    # Tokens issued before session versions existed carry no claim and count as version 0.
    return token.get(SESSION_VERSION_CLAIM, 0) == user.session_version


def end_all_sessions(user):
    """Sign the user out everywhere: older tokens stop working on their next request."""
    user.session_version += 1
    user.save(update_fields=["session_version"])
    for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
        BlacklistedToken.objects.get_or_create(token=token)


class PasswordCheck(Enum):
    OK = "ok"
    WRONG = "wrong"
    LOCKED = "locked"


def check_current_password(user, password: str) -> PasswordCheck:
    """Re-check the password before a sensitive change.

    Wrong guesses share the login lockout counter, so a stolen session can't be used to
    brute-force the password. Reaching the limit locks the account and signs it out everywhere.
    """
    now = timezone.now()
    if user.locked_until and user.locked_until > now:
        return PasswordCheck.LOCKED
    if user.check_password(password):
        if user.failed_login_attempts:
            user.failed_login_attempts = 0
            user.save(update_fields=["failed_login_attempts"])
        return PasswordCheck.OK

    user.failed_login_attempts += 1
    if user.failed_login_attempts < MAX_PASSWORD_ATTEMPTS:
        user.save(update_fields=["failed_login_attempts"])
        return PasswordCheck.WRONG
    user.failed_login_attempts = 0
    user.locked_until = now + LOCKOUT_DURATION
    user.save(update_fields=["failed_login_attempts", "locked_until"])
    end_all_sessions(user)
    return PasswordCheck.LOCKED


def send_after_commit(send, *args):
    """Send a security alert once the change is saved. A failed alert must not undo the change."""

    def run():
        try:
            send(*args)
        except Exception:
            logger.exception("Could not send security email (%s)", send.__name__)

    transaction.on_commit(run)


# --- Email change -------------------------------------------------------------


def _code_hash(user, new_email: str, code: str) -> str:
    message = f"email-change:{user.pk}:{new_email}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def start_email_change(user, new_email: str) -> str:
    """Store a pending change and return the code to email to the new address."""
    code = f"{secrets.randbelow(10**6):06d}"
    now = timezone.now()
    EmailChangeRequest.objects.update_or_create(
        user=user,
        defaults={
            "new_email": new_email,
            "code_hash": _code_hash(user, new_email, code),
            "created_at": now,
            "expires_at": now + EMAIL_CODE_TTL,
            "attempts": 0,
        },
    )
    return code


class CodeCheck(Enum):
    OK = "ok"
    INVALID = "invalid"
    TOO_MANY_ATTEMPTS = "too_many_attempts"


def check_email_change_code(user, code: str):
    """Returns (result, pending request). The request is only usable when the result is OK."""
    pending = EmailChangeRequest.objects.filter(user=user).first()
    if not pending or pending.expires_at <= timezone.now():
        return CodeCheck.INVALID, None
    if pending.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
        return CodeCheck.TOO_MANY_ATTEMPTS, None
    if not hmac.compare_digest(pending.code_hash, _code_hash(user, pending.new_email, code.strip())):
        pending.attempts += 1
        pending.save(update_fields=["attempts"])
        result = CodeCheck.TOO_MANY_ATTEMPTS if pending.attempts >= EMAIL_CODE_MAX_ATTEMPTS else CodeCheck.INVALID
        return result, None
    return CodeCheck.OK, pending


def make_revert_token(user, old_email: str) -> str:
    return signing.dumps({"user": str(user.pk), "old_email": old_email}, salt=REVERT_SALT)


def read_revert_token(token: str):
    """Returns (user_id, old_email), or None if the link is invalid or older than the undo window."""
    try:
        data = signing.loads(token, salt=REVERT_SALT, max_age=REVERT_WINDOW)
    except signing.BadSignature:
        return None
    return data["user"], data["old_email"]
