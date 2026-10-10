"""Sending SMS through Africa's Talking.

SMS_BACKEND picks where messages go:
- "console" (default, local development): logged, nothing is sent;
- "locmem" (tests): appended to `outbox`;
- "africastalking" (production): sent for real. Needs AFRICASTALKING_USERNAME and
  AFRICASTALKING_API_KEY; use username "sandbox" with a sandbox key to test for free.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

outbox: list[dict] = []

LIVE_URL = "https://api.africastalking.com/version1/messaging"
SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
# Africa's Talking per-recipient status codes that mean the message was accepted.
ACCEPTED_CODES = {100, 101, 102}


class SMSError(Exception):
    pass


def send_sms(to: str, message: str):
    backend = settings.SMS_BACKEND
    if backend == "locmem":
        outbox.append({"to": to, "message": message})
        return
    if backend == "console":
        logger.info("SMS to %s: %s", to, message)
        return
    if backend != "africastalking":
        raise SMSError(f"Unknown SMS_BACKEND {backend!r}.")
    if not settings.AFRICASTALKING_API_KEY:
        raise SMSError("AFRICASTALKING_API_KEY is not set, so no SMS can be sent.")

    username = settings.AFRICASTALKING_USERNAME
    data = {"username": username, "to": to, "message": message}
    if settings.AFRICASTALKING_SENDER_ID:
        data["from"] = settings.AFRICASTALKING_SENDER_ID
    response = requests.post(
        SANDBOX_URL if username == "sandbox" else LIVE_URL,
        data=data,
        headers={"apiKey": settings.AFRICASTALKING_API_KEY, "Accept": "application/json"},
        timeout=15,
    )
    if response.status_code >= 400:
        raise SMSError(f"Africa's Talking rejected the SMS ({response.status_code}): {response.text}")
    recipients = response.json().get("SMSMessageData", {}).get("Recipients", [])
    if not recipients or recipients[0].get("statusCode") not in ACCEPTED_CODES:
        raise SMSError(f"SMS to {to} was not accepted: {response.text}")
