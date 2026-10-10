from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from .cookies import ACCESS_COOKIE, enforce_csrf
from .security import token_is_current


class CookieJWTAuthentication(JWTAuthentication):
    """Reads the access token from its httpOnly cookie (the browser app), falling back to an
    Authorization: Bearer header (API clients/docs). Cookie auth must pass CSRF; header auth
    can't be forged cross-site, so it doesn't need to."""

    def authenticate(self, request):
        if self.get_header(request) is not None:
            return super().authenticate(request)

        raw_token = request.COOKIES.get(ACCESS_COOKIE)
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        enforce_csrf(request)
        return user, validated_token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not token_is_current(validated_token, user):
            raise AuthenticationFailed("This session has ended. Please sign in again.", code="session_revoked")
        return user


class CookieJWTScheme(OpenApiAuthenticationExtension):
    """Describes the cookie auth in /api/docs (registered on import)."""

    target_class = "apps.accounts.authentication.CookieJWTAuthentication"
    name = "cookieJWT"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": ACCESS_COOKIE}
