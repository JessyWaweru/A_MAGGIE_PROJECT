import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa

DEBUG = False

# Everything signed (password reset links, verification codes, undo links) depends on this key.
# Refuse to start with the placeholder or a short one rather than run with forgeable links.
if SECRET_KEY.startswith("django-insecure") or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Set SECRET_KEY to a long random value (50+ characters) in production.")

# Render sets this automatically; add it so the health check and API calls
# to the assigned *.onrender.com domain aren't rejected by ALLOWED_HOSTS.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Send through Resend's HTTPS API: Render's free tier blocks outbound SMTP ports, and the
# console default in base.py would silently swallow every email.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="apps.core.email_backend.ResendEmailBackend")

# With an Africa's Talking key, riders are texted automatically; without one, staff send
# the rider message themselves from the order page ("manual").
SMS_BACKEND = env("SMS_BACKEND", default="africastalking" if env("AFRICASTALKING_API_KEY", default="") else "manual")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
