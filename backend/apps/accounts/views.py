import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, permissions, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import REFRESH_COOKIE, clear_auth_cookies, enforce_csrf, set_auth_cookies

from .emails import (
    send_email_change_code,
    send_email_changed_alert,
    send_password_changed_alert,
    send_password_reset_email,
    send_welcome_email,
)
from .models import Address, EmailChangeRequest
from .security import (
    CodeCheck as EmailCodeCheck,
    PasswordCheck,
    check_current_password,
    check_email_change_code,
    end_all_sessions,
    issue_refresh_token,
    make_revert_token,
    read_revert_token,
    send_after_commit,
    start_email_change,
    token_is_current,
)
from .serializers import (
    AddressSerializer,
    ChangePasswordSerializer,
    ConfirmEmailChangeSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    RevertEmailChangeSerializer,
    StartEmailChangeSerializer,
    UserSerializer,
    VerifyCodeSerializer,
)
from .turnstile import passes_turnstile
from .verification import RESEND_COOLDOWN, CodeCheck, check_code, issue_code, seconds_until_resend

logger = logging.getLogger(__name__)
User = get_user_model()


MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
INVALID_CODE_MESSAGE = "That code is incorrect or has expired."


def _invalid_credentials():
    return Response({"detail": "Incorrect email or password."}, status=status.HTTP_401_UNAUTHORIZED)


def _bot_check_failed():
    return Response(
        {"detail": "We couldn't confirm you're human. Please complete the check and try again.", "code": "bot_check_failed"},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _session_for(request, user):
    """Sign a verified user in: tokens go into httpOnly cookies, only the profile goes in the body."""
    update_last_login(None, user)
    response = Response({"user": UserSerializer(user).data})
    return set_auth_cookies(response, issue_refresh_token(user))


def _locked_out():
    """The current-password check hit the limit: the account is locked and signed out everywhere."""
    response = Response(
        {
            "detail": "Too many incorrect passwords. For your security you've been signed out. "
            "Try again in 15 minutes, or reset your password.",
            "code": "account_locked",
        },
        status=status.HTTP_403_FORBIDDEN,
    )
    return clear_auth_cookies(response)


def _wrong_password():
    return Response({"detail": "Your current password is incorrect.", "code": "wrong_password"}, status=400)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    """Hands the SPA a CSRF token. It can't read the API's cookies cross-origin, so it gets it here."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(generics.CreateAPIView):
    """Creates the account and emails a code. No session until the code is confirmed."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        if not passes_turnstile(request, request.data.get("turnstile_token", "")):
            return _bot_check_failed()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # If the code can't be emailed, roll the account back so the user can simply retry.
        with transaction.atomic():
            user = serializer.save()
            issue_code(user)
        return Response(
            {
                "email": user.email,
                "detail": f"We've sent a 6-digit code to {user.email}.",
                "resend_in": seconds_until_resend(user),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user = User.objects.filter(email__iexact=email).first()
        now = timezone.now()

        if user and user.locked_until and user.locked_until > now:
            minutes = max(1, round((user.locked_until - now).total_seconds() / 60))
            return Response(
                {
                    "detail": f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
                    "code": "account_locked",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if user is None:
            # Hash anyway so response time doesn't reveal whether the email is registered.
            User().set_password(password)
            return _invalid_credentials()

        if not user.check_password(password) or not user.is_active:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_LOGINS:
                user.failed_login_attempts = 0
                user.locked_until = now + LOCKOUT_DURATION
            user.save(update_fields=["failed_login_attempts", "locked_until"])
            return _invalid_credentials()

        if user.failed_login_attempts or user.locked_until:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_login_attempts", "locked_until"])

        if not user.is_email_verified:
            issue_code(user)
            return Response(
                {
                    "detail": f"Please verify your email first — we've sent a code to {user.email}.",
                    "code": "email_not_verified",
                    "email": user.email,
                    "resend_in": seconds_until_resend(user),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return _session_for(request, user)


def _refresh_token_is_current(raw: str) -> bool:
    """False if the token is invalid or belongs to a session ended by a password/email change."""
    try:
        token = RefreshToken(raw)
    except TokenError:
        return False
    user = User.objects.filter(pk=token.get("user_id")).first()
    return user is not None and user.is_active and token_is_current(token, user)


class CookieTokenRefreshView(APIView):
    """Rotates the refresh cookie and issues a fresh access cookie."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        enforce_csrf(request)
        raw = request.COOKIES.get(REFRESH_COOKIE, "")
        if not _refresh_token_is_current(raw):
            return clear_auth_cookies(
                Response({"detail": "Your session has expired. Please sign in again."}, status=status.HTTP_401_UNAUTHORIZED)
            )
        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, ValidationError):
            return clear_auth_cookies(
                Response({"detail": "Your session has expired. Please sign in again."}, status=status.HTTP_401_UNAUTHORIZED)
            )
        # With rotation on, the serializer returns a new refresh token and blacklists the old one.
        refresh = RefreshToken(serializer.validated_data["refresh"])
        return set_auth_cookies(Response({"detail": "Session refreshed."}), refresh)


class LogoutView(APIView):
    """Blacklists the refresh token and clears both cookies, even if the access token already expired."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        enforce_csrf(request)
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        return clear_auth_cookies(Response(status=status.HTTP_204_NO_CONTENT))


class VerifyEmailView(APIView):
    """Confirms the emailed code and signs the user in."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify_code"

    def post(self, request):
        enforce_csrf(request)
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user is None or user.is_email_verified:
            return Response({"detail": INVALID_CODE_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)

        result = check_code(user, serializer.validated_data["code"])
        if result is CodeCheck.TOO_MANY_ATTEMPTS:
            return Response(
                {"detail": "Too many incorrect attempts. Request a new code.", "code": "too_many_attempts"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if result is CodeCheck.INVALID:
            return Response({"detail": INVALID_CODE_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        try:
            send_welcome_email(user)
        except Exception:
            logger.exception("Welcome email failed for %s", user.pk)
        return _session_for(request, user)


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "resend_code"

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user and not user.is_email_verified:
            issue_code(user)
        # Same response regardless, so we don't leak which emails are registered.
        return Response(
            {
                "detail": "If that account needs verifying, we've sent a new code.",
                "resend_in": int(RESEND_COOLDOWN.total_seconds()),
            }
        )


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        if not passes_turnstile(request, request.data.get("turnstile_token", "")):
            return _bot_check_failed()
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email__iexact=serializer.validated_data["email"])
            send_password_reset_email(user)
        except User.DoesNotExist:
            pass
        return Response({"detail": "If that account exists, a password reset email has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        # The reset link proves inbox ownership, so it also clears any lockout and verifies the email.
        user.failed_login_attempts = 0
        user.locked_until = None
        user.is_email_verified = True
        user.save(update_fields=["password", "failed_login_attempts", "locked_until", "is_email_verified"])
        # Whoever else was signed in (possibly the reason for the reset) is signed out.
        end_all_sessions(user)
        send_after_commit(send_password_changed_alert, user)
        return Response({"detail": "Password has been reset. You can now log in."})


class ChangePasswordView(APIView):
    """Needs the current password. Signs out every other device and emails an alert."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive"

    @transaction.atomic
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        check = check_current_password(user, serializer.validated_data["old_password"])
        if check is PasswordCheck.LOCKED:
            return _locked_out()
        if check is PasswordCheck.WRONG:
            return _wrong_password()

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        end_all_sessions(user)
        send_after_commit(send_password_changed_alert, user)
        # This device stays signed in with a fresh session.
        response = Response({"detail": "Password changed. You've been signed out on all other devices."})
        return set_auth_cookies(response, issue_refresh_token(user))


class StartEmailChangeView(APIView):
    """Step 1: re-check the password, then email a code to the new address."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive"

    @transaction.atomic
    def post(self, request):
        serializer = StartEmailChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        check = check_current_password(user, serializer.validated_data["password"])
        if check is PasswordCheck.LOCKED:
            return _locked_out()
        if check is PasswordCheck.WRONG:
            return _wrong_password()

        new_email = serializer.validated_data["new_email"]
        code = start_email_change(user, new_email)
        send_email_change_code(user, new_email, code)
        return Response({"detail": f"We've sent a 6-digit code to {new_email}.", "new_email": new_email})


class ConfirmEmailChangeView(APIView):
    """Step 2: the code proves the user owns the new address. Then the old address is alerted."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify_code"

    @transaction.atomic
    def post(self, request):
        serializer = ConfirmEmailChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        result, pending = check_email_change_code(user, serializer.validated_data["code"])
        if result is EmailCodeCheck.TOO_MANY_ATTEMPTS:
            return Response(
                {"detail": "Too many incorrect codes. Start the email change again.", "code": "too_many_attempts"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if result is EmailCodeCheck.INVALID:
            return Response({"detail": INVALID_CODE_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)

        new_email = pending.new_email
        # Someone may have registered the address while the code was in the post.
        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            pending.delete()
            return Response({"detail": "That email address is already in use."}, status=status.HTTP_400_BAD_REQUEST)

        old_email = user.email
        user.email = new_email
        user.username = new_email
        user.is_email_verified = True
        user.save(update_fields=["email", "username", "is_email_verified"])
        pending.delete()
        end_all_sessions(user)
        send_after_commit(send_email_changed_alert, user, old_email, make_revert_token(user, old_email))

        response = Response({"detail": "Your email has been changed.", "user": UserSerializer(user).data})
        return set_auth_cookies(response, issue_refresh_token(user))


class RevertEmailChangeView(APIView):
    """The undo link emailed to the old address: restores it, signs everyone out and sends a reset link."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @transaction.atomic
    def post(self, request):
        serializer = RevertEmailChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parsed = read_revert_token(serializer.validated_data["token"])
        user = User.objects.select_for_update().filter(pk=parsed[0]).first() if parsed else None
        if user is None:
            return Response(
                {"detail": "This link is invalid or has expired. Contact us and we'll help secure your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_email = parsed[1]
        if user.email.lower() != old_email.lower():
            if User.objects.filter(email__iexact=old_email).exclude(pk=user.pk).exists():
                return Response(
                    {"detail": "That address now belongs to another account. Contact us and we'll help."},
                    status=status.HTTP_409_CONFLICT,
                )
            user.email = old_email
            user.username = old_email
            user.is_email_verified = True
            user.save(update_fields=["email", "username", "is_email_verified"])
        EmailChangeRequest.objects.filter(user=user).delete()
        end_all_sessions(user)
        send_after_commit(send_password_reset_email, user)
        return Response(
            {
                "detail": f"Your account email is back to {old_email} and everyone has been signed out. "
                "We've sent you a link to set a new password."
            }
        )


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
