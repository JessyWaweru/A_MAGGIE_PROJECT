from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    AddressViewSet,
    ChangePasswordView,
    CookieTokenRefreshView,
    CsrfTokenView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendVerificationView,
    VerifyEmailView,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("login/refresh/", CookieTokenRefreshView.as_view(), name="auth-login-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("verify-email/resend/", ResendVerificationView.as_view(), name="auth-resend-verification"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("", include(router.urls)),
]
