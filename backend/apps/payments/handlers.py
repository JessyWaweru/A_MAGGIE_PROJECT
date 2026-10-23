import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.emails import send_after_commit, send_consultation_confirmed_emails, send_order_confirmation_email
from apps.consultations.models import Consultation
from apps.orders.models import Order
from apps.products.models import Product

from .models import Payment
from .services import payment_record, to_subunit

logger = logging.getLogger(__name__)


def _paid_in_full(payment: Payment, verify_data: dict) -> bool:
    """Paystack says "success" for whatever was charged; make sure that's this payment's full price."""
    try:
        amount = int(verify_data.get("amount"))
    except (TypeError, ValueError):
        return False
    currency = (verify_data.get("currency") or "").upper()
    return amount == to_subunit(payment.amount) and currency == payment.currency.upper()


@transaction.atomic
def fulfill_successful_payment(payment: Payment, verify_data: dict):
    """Idempotently mark a payment as paid, then fulfil what it paid for.

    For an order: mark it paid and decrement stock. For a consultation: confirm the booking.

    Safe to call multiple times (e.g. once from the client-triggered verify
    call and once from the Paystack webhook) - only acts the first time.
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.Status.SUCCESS:
        return payment

    if not _paid_in_full(payment, verify_data):
        # Never fulfil on a short or wrong-currency charge; leave it for the team to look at.
        logger.error(
            "Payment %s: Paystack charged %s %s but %s %s was due. Not fulfilling.",
            payment.reference,
            verify_data.get("amount"),
            verify_data.get("currency"),
            to_subunit(payment.amount),
            payment.currency,
        )
        payment.status = Payment.Status.FAILED
        payment.raw_response = payment_record(verify_data)
        payment.save(update_fields=["status", "raw_response", "updated_at"])
        return payment

    payment.status = Payment.Status.SUCCESS
    payment.channel = verify_data.get("channel", "")
    payment.paid_at = timezone.now()
    payment.raw_response = payment_record(verify_data)
    payment.save(update_fields=["status", "channel", "paid_at", "raw_response", "updated_at"])

    if payment.consultation_id:
        _confirm_consultation(payment)
        return payment

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

        send_after_commit(send_order_confirmation_email, order)

    return payment


def _confirm_consultation(payment):
    consultation = Consultation.objects.select_for_update().get(pk=payment.consultation_id)
    if consultation.status == Consultation.Status.PENDING_PAYMENT:
        consultation.status = Consultation.Status.CONFIRMED
        consultation.paid_at = timezone.now()
        consultation.save(update_fields=["status", "paid_at", "updated_at"])
        send_after_commit(send_consultation_confirmed_emails, consultation)
