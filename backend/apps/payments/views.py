import hashlib
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.consultations.models import Consultation
from apps.orders.models import Order

from .handlers import fulfill_successful_payment
from .models import Payment
from .serializers import InitializePaymentSerializer, MpesaChargeSerializer, PaymentSerializer
from .services import PaystackError, charge_mpesa, initialize_transaction, payment_record, verify_transaction


# Paystack's statuses for a transaction that may still succeed (an M-Pesa prompt waiting for a PIN).
STILL_PENDING = {"pay_offline", "ongoing", "pending", "processing", "queued"}

# How long an M-Pesa prompt stays open on the customer's phone (set by Safaricom).
MPESA_PROMPT_WINDOW = timedelta(seconds=180)


class NotPayable(APIException):
    status_code = status.HTTP_400_BAD_REQUEST


def _new_payment(user, data):
    """Start a Payment for the order or booking `user` is paying for.

    Returns the payment, the frontend path to come back to, and the metadata to send Paystack.
    """
    if data.get("order_number"):
        order = get_object_or_404(Order, order_number=data["order_number"], user=user)
        if order.status != Order.Status.PENDING:
            raise NotPayable("This order has already been paid or is no longer payable.")
        payment = Payment(order=order, amount=order.total_amount, currency=order.currency)
        return payment, f"/orders/{order.order_number}", {"order_number": order.order_number, "user_id": str(user.id)}

    consultation = get_object_or_404(Consultation, reference=data["consultation_reference"], user=user)
    if consultation.status != Consultation.Status.PENDING_PAYMENT:
        raise NotPayable("This booking has already been paid or is no longer payable.")
    payment = Payment(consultation=consultation, amount=consultation.fee, currency=consultation.currency)
    return (
        payment,
        f"/consultations/{consultation.reference}",
        {"consultation_reference": consultation.reference, "user_id": str(user.id)},
    )


class InitializePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "create"

    def post(self, request):
        serializer = InitializePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, path, metadata = _new_payment(request.user, serializer.validated_data)
        payment.save()
        callback_url = f"{settings.FRONTEND_URL}{path}"

        try:
            data = initialize_transaction(
                email=request.user.email,
                amount=payment.amount,
                reference=payment.reference,
                callback_url=callback_url,
                metadata=metadata,
            )
        except PaystackError as exc:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        payment.authorization_url = data.get("authorization_url", "")
        payment.save(update_fields=["authorization_url", "updated_at"])

        return Response(
            {
                "authorization_url": payment.authorization_url,
                "reference": payment.reference,
                "public_key": settings.PAYSTACK_PUBLIC_KEY,
            },
            status=status.HTTP_201_CREATED,
        )


class MpesaChargeView(APIView):
    """Sends an M-Pesa prompt straight to the customer's phone; the page then polls verify."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "create"

    def post(self, request):
        serializer = MpesaChargeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, _, metadata = _new_payment(request.user, serializer.validated_data)

        # A second prompt while the first is still open could charge the customer twice.
        open_prompt = Payment.objects.filter(
            order=payment.order, consultation=payment.consultation, channel="mobile_money",
            status=Payment.Status.PENDING, created_at__gte=timezone.now() - MPESA_PROMPT_WINDOW,
        )
        if open_prompt.exists():
            return Response(
                {"detail": "We've already sent an M-Pesa prompt for this. Check your phone, or try again in 3 minutes."},
                status=status.HTTP_409_CONFLICT,
            )

        payment.channel = "mobile_money"
        payment.save()
        try:
            # The phone number goes to Paystack only; we don't store it with the payment.
            data = charge_mpesa(
                email=request.user.email,
                amount=payment.amount,
                reference=payment.reference,
                phone=serializer.validated_data["phone_number"],
                metadata=metadata,
            )
        except PaystackError as exc:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        charge_status = data.get("status")
        if charge_status == "success":
            payment = fulfill_successful_payment(payment, data)
        elif charge_status not in STILL_PENDING:
            # e.g. "failed", or a step (OTP, redirect) this flow can't show; the Paystack page can.
            payment.status = Payment.Status.FAILED
            payment.raw_response = payment_record(data)
            payment.save(update_fields=["status", "raw_response", "updated_at"])
            return Response(
                {"detail": data.get("message") or "M-Pesa couldn't take this payment. Try again, or pay on the Paystack page."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "reference": payment.reference,
                "status": payment.status,
                "display_text": data.get("display_text") or "Check your phone and enter your M-Pesa PIN.",
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, reference):
        payment = get_object_or_404(
            Payment, Q(order__user=request.user) | Q(consultation__user=request.user), reference=reference
        )

        if payment.status == Payment.Status.SUCCESS:
            return Response(PaymentSerializer(payment).data)

        try:
            data = verify_transaction(reference)
        except PaystackError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if data.get("status") == "success":
            payment = fulfill_successful_payment(payment, data)
        elif data.get("status") not in STILL_PENDING:
            payment.status = Payment.Status.FAILED
            payment.raw_response = payment_record(data)
            payment.save(update_fields=["status", "raw_response", "updated_at"])

        return Response(PaymentSerializer(payment).data)


class PaystackWebhookView(APIView):
    """Receives async payment events directly from Paystack, verified via HMAC signature."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get("X-Paystack-Signature", "")
        computed = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode("utf-8"), request.body, hashlib.sha512
        ).hexdigest()
        if not settings.PAYSTACK_SECRET_KEY or not hmac.compare_digest(signature, computed):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        event = json.loads(request.body)
        if event.get("event") == "charge.success":
            data = event["data"]
            reference = data.get("reference")
            payment = Payment.objects.filter(reference=reference).first()
            if payment:
                fulfill_successful_payment(payment, data)

        return Response(status=status.HTTP_200_OK)
