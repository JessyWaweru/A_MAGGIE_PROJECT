from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    AddressViewSet,
    ChangePasswordView,
    ConfirmEmailChangeView,
    CookieTokenRefreshView,
    CsrfTokenView,
    DeleteAccountView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendVerificationView,
    RevertEmailChangeView,
    StartEmailChangeView,
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
    path("change-email/", StartEmailChangeView.as_view(), name="auth-change-email"),
    path("change-email/confirm/", ConfirmEmailChangeView.as_view(), name="auth-change-email-confirm"),
    path("change-email/revert/", RevertEmailChangeView.as_view(), name="auth-change-email-revert"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("delete-account/", DeleteAccountView.as_view(), name="auth-delete-account"),
    path("", include(router.urls)),
]
