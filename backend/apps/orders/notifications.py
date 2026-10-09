import logging

from django.db import transaction

from apps.accounts.emails import send_order_status_email

from .models import Order

logger = logging.getLogger(__name__)

# Statuses worth an email; "paid" already gets the order confirmation.
NOTIFY_STATUSES = {
    Order.Status.READY_FOR_PICKUP,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
}


def notify_status_change(order):
    if order.status not in NOTIFY_STATUSES:
        return

    def send():
        try:
            send_order_status_email(order)
        except Exception:
            # A failed email must never block staff from updating an order.
            logger.exception("Could not email status update for order %s", order.order_number)

    transaction.on_commit(send)
