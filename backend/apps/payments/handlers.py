from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.emails import send_order_confirmation_email
from apps.orders.models import Order
from apps.products.models import Product

from .models import Payment


@transaction.atomic
def fulfill_successful_payment(payment: Payment, verify_data: dict):
    """Idempotently mark a payment + its order as paid and decrement stock.

    Safe to call multiple times (e.g. once from the client-triggered verify
    call and once from the Paystack webhook) - only acts the first time.
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.Status.SUCCESS:
        return payment

    payment.status = Payment.Status.SUCCESS
    payment.channel = verify_data.get("channel", "")
    payment.paid_at = timezone.now()
    payment.raw_response = verify_data
    payment.save(update_fields=["status", "channel", "paid_at", "raw_response", "updated_at"])

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status == Order.Status.PENDING:
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])

        for item in order.items.all():
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(
                    stock_quantity=F("stock_quantity") - item.quantity
                )

        send_order_confirmation_email(order)

    return payment
