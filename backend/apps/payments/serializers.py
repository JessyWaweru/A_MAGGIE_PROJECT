import re

from rest_framework import serializers

from .models import Payment


class InitializePaymentSerializer(serializers.Serializer):
    order_number = serializers.CharField(required=False)
    consultation_reference = serializers.CharField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("order_number")) == bool(attrs.get("consultation_reference")):
            raise serializers.ValidationError("Provide either order_number or consultation_reference.")
        return attrs


class MpesaChargeSerializer(InitializePaymentSerializer):
    phone_number = serializers.CharField(max_length=20)

    def validate_phone_number(self, value):
        """Accept the ways Kenyans write a Safaricom number and return Paystack's +254 form."""
        digits = re.sub(r"[\s\-()]", "", value).removeprefix("+")
        if digits.startswith("254"):
            digits = digits[3:]
        elif digits.startswith("0"):
            digits = digits[1:]
        if not re.fullmatch(r"[71]\d{8}", digits):
            raise serializers.ValidationError("Enter an M-Pesa number like 0712 345 678.")
        return f"+254{digits}"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "reference", "status", "amount", "currency", "channel", "paid_at", "created_at"]
        read_only_fields = fields
