from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

from .security import LOCKOUT_DURATION, MAX_PASSWORD_ATTEMPTS


class LockoutModelBackend(ModelBackend):
    """Gives Django's own sign-in (the admin) the same lockout as the API login: after five wrong
    passwords the account refuses every password, right or wrong, for a few minutes."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        user = User.objects.filter(email__iexact=username).first()
        if user is None:
            # Hash anyway so response time doesn't reveal whether the email is registered.
            User().set_password(password)
            return None

        now = timezone.now()
        if user.locked_until and user.locked_until > now:
            return None

        if not (user.check_password(password) and self.user_can_authenticate(user)):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_PASSWORD_ATTEMPTS:
                user.failed_login_attempts = 0
                user.locked_until = now + LOCKOUT_DURATION
            user.save(update_fields=["failed_login_attempts", "locked_until"])
            return None

        if user.failed_login_attempts or user.locked_until:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_login_attempts", "locked_until"])
        return user
