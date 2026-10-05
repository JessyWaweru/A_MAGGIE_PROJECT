"""JWTs live in httpOnly cookies so page JavaScript (and any injected script) can never read them.

Because browsers attach cookies automatically, every unsafe request authenticated by
cookie must also pass Django's CSRF check (token from GET /api/auth/csrf/, sent back
in the X-CSRFToken header).
"""

from django.conf import settings
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken

ACCESS_COOKIE = "goherbal_access"
REFRESH_COOKIE = "goherbal_refresh"
# The refresh token is only ever needed by the auth endpoints, so it's never sent anywhere else.
REFRESH_COOKIE_PATH = "/api/auth/"


def _cookie_kwargs():
    return {
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "domain": settings.AUTH_COOKIE_DOMAIN,
    }


def set_auth_cookies(response, refresh: RefreshToken):
    jwt = settings.SIMPLE_JWT
    response.set_cookie(
        ACCESS_COOKIE,
        str(refresh.access_token),
        max_age=int(jwt["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        path="/",
        **_cookie_kwargs(),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        str(refresh),
        max_age=int(jwt["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=REFRESH_COOKIE_PATH,
        **_cookie_kwargs(),
    )
    return response


def clear_auth_cookies(response):
    kwargs = {"samesite": settings.AUTH_COOKIE_SAMESITE, "domain": settings.AUTH_COOKIE_DOMAIN}
    response.delete_cookie(ACCESS_COOKIE, path="/", **kwargs)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, **kwargs)
    return response


def enforce_csrf(request):
    """Same check DRF's SessionAuthentication performs, for views that read auth cookies."""
    check = CSRFCheck(lambda req: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied(f"CSRF Failed: {reason}")
