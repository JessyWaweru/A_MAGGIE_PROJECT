"""Sending a delivery to a rider: an SMS with a private link to the rider page."""

from django.conf import settings

from apps.core.sms import send_sms


def rider_link(order) -> str:
    return f"{settings.FRONTEND_URL}/r/{order.rider_token}"


def text_rider(order):
    """SMS the assigned rider their link. Kept short: one SMS is 160 characters."""
    send_sms(
        order.rider.phone_number,
        f"GOherbal delivery {order.order_number} for {order.full_name.split(' ')[0]}. "
        f"Details, map and buttons: {rider_link(order)}",
    )
