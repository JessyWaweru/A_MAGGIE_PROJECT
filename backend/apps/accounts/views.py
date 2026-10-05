import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
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

from .emails import send_password_reset_email, send_welcome_email
from .models import Address
from .serializers import (
    AddressSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
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
    return set_auth_cookies(response, RefreshToken.for_user(user))


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


class CookieTokenRefreshView(APIView):
    """Rotates the refresh cookie and issues a fresh access cookie."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        enforce_csrf(request)
        serializer = TokenRefreshSerializer(data={"refresh": request.COOKIES.get(REFRESH_COOKIE, "")})
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
        return Response({"detail": "Password has been reset. You can now log in."})


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password changed successfully."})


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
