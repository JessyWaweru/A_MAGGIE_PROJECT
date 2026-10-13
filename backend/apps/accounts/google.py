"""Verifies the ID token Google's sign-in button hands the browser."""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_credential(credential: str) -> dict | None:
    """Return the token's claims if Google issued it for this site and the email is verified."""
    if not (credential and settings.GOOGLE_CLIENT_ID):
        return None
    try:
        # Google checks the signature and expiry; an invalid token comes back as a 400.
        response = requests.get(TOKENINFO_URL, params={"id_token": credential}, timeout=10)
    except requests.RequestException:
        logger.exception("Could not reach Google to verify a sign-in token.")
        return None
    if response.status_code != 200:
        return None
    claims = response.json()
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID or claims.get("iss") not in GOOGLE_ISSUERS:
        return None
    if str(claims.get("email_verified")).lower() != "true" or not claims.get("email"):
        return None
    return claims
