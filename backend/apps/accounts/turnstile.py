"""Cloudflare Turnstile bot check for endpoints that send email to arbitrary addresses."""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def passes_turnstile(request, token: str) -> bool:
    """Fails closed: no secret configured, no token, or Cloudflare unreachable all count as a failure."""
    secret = settings.TURNSTILE_SECRET_KEY
    if not secret:
        logger.error("TURNSTILE_SECRET_KEY is not configured; rejecting request.")
        return False
    if not token:
        return False
    try:
        response = requests.post(
            VERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": client_ip(request)},
            timeout=5,
        )
        result = response.json()
    except (requests.RequestException, ValueError):
        logger.exception("Turnstile verification request failed.")
        return False
    if not result.get("success"):
        logger.info("Turnstile rejected a token: %s", result.get("error-codes"))
    return bool(result.get("success"))
