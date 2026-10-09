import hashlib
import hmac
import json

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.consultations.models import Consultation
from apps.orders.models import Order

from .handlers import fulfill_successful_payment
from .models import Payment
from .serializers import InitializePaymentSerializer, PaymentSerializer
from .services import PaystackError, initialize_transaction, verify_transaction


class InitializePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = InitializePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("order_number"):
            order = get_object_or_404(
                Order, order_number=serializer.validated_data["order_number"], user=request.user
            )
            if order.status != Order.Status.PENDING:
                return Response({"detail": "This order has already been paid or is no longer payable."}, status=400)
            payment = Payment.objects.create(order=order, amount=order.total_amount, currency=order.currency)
            callback_url = f"{settings.FRONTEND_URL}/orders/{order.order_number}"
            metadata = {"order_number": order.order_number, "user_id": str(request.user.id)}
        else:
            consultation = get_object_or_404(
                Consultation, reference=serializer.validated_data["consultation_reference"], user=request.user
            )
            if consultation.status != Consultation.Status.PENDING_PAYMENT:
                return Response({"detail": "This booking has already been paid or is no longer payable."}, status=400)
            payment = Payment.objects.create(
                consultation=consultation, amount=consultation.fee, currency=consultation.currency
            )
            callback_url = f"{settings.FRONTEND_URL}/consultations/{consultation.reference}"
            metadata = {"consultation_reference": consultation.reference, "user_id": str(request.user.id)}

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
        else:
            payment.status = Payment.Status.FAILED
            payment.raw_response = data
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
