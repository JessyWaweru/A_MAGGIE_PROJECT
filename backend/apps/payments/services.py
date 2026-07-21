import requests
from django.conf import settings


class PaystackError(Exception):
    pass


def _headers():
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


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
