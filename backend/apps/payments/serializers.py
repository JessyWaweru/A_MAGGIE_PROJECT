from rest_framework import serializers

from .models import Payment


class InitializePaymentSerializer(serializers.Serializer):
    order_number = serializers.CharField(required=False)
    consultation_reference = serializers.CharField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("order_number")) == bool(attrs.get("consultation_reference")):
            raise serializers.ValidationError("Provide either order_number or consultation_reference.")
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "reference", "status", "amount", "currency", "channel", "paid_at", "created_at"]
        read_only_fields = fields
