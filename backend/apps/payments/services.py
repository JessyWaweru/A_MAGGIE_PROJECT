import requests
from django.conf import settings


class PaystackError(Exception):
    pass


def _headers():
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


# What we keep from Paystack's transaction data: enough to reconcile, nothing personal
# (Paystack also sends the payer's IP address, email and card details, which we don't need).
PAYMENT_RECORD_FIELDS = ("id", "status", "reference", "amount", "currency", "channel", "gateway_response", "paid_at", "fees")


def payment_record(data: dict) -> dict:
    return {key: data[key] for key in PAYMENT_RECORD_FIELDS if key in data}


def to_subunit(amount) -> int:
    """Paystack expects amounts in the smallest currency unit (e.g. cents/kobo)."""
    return int(round(amount * 100))


def initialize_transaction(email: str, amount, reference: str, callback_url: str, metadata: dict | None = None):
    response = requests.post(
        f"{settings.PAYSTACK_BASE_URL}/transaction/initialize",
        headers=_headers(),
        json={
            "email": email,
            "amount": to_subunit(amount),
            "reference": reference,
            "callback_url": callback_url,
            "currency": settings.PAYMENT_CURRENCY,
            "metadata": metadata or {},
        },
        timeout=15,
    )
    data = response.json()
    if not response.ok or not data.get("status"):
        raise PaystackError(data.get("message", "Failed to initialize payment."))
    return data["data"]


def charge_mpesa(email: str, amount, reference: str, phone: str, metadata: dict | None = None):
    """Send an M-Pesa prompt (STK push) straight to the customer's phone, without the Paystack page.

    Paystack answers "pay_offline" while it waits for the customer's PIN; the outcome then arrives
    as a charge.success webhook, or through verify_transaction. The customer has 180 seconds.
    """
    response = requests.post(
        f"{settings.PAYSTACK_BASE_URL}/charge",
        headers=_headers(),
        json={
            "email": email,
            "amount": to_subunit(amount),
            "reference": reference,
            "currency": settings.PAYMENT_CURRENCY,
            "mobile_money": {"phone": phone, "provider": "mpesa"},
            "metadata": metadata or {},
        },
        timeout=30,
    )
    data = response.json()
    if not response.ok or not data.get("status"):
        raise PaystackError(data.get("message", "Failed to send the M-Pesa prompt."))
    return data["data"]


def verify_transaction(reference: str):
    response = requests.get(
        f"{settings.PAYSTACK_BASE_URL}/transaction/verify/{reference}",
        headers=_headers(),
        timeout=15,
    )
    data = response.json()
    if not response.ok or not data.get("status"):
        raise PaystackError(data.get("message", "Failed to verify payment."))
    return data["data"]
