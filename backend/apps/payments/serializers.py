from rest_framework import serializers

from .models import Payment


class InitializePaymentSerializer(serializers.Serializer):
    order_number = serializers.CharField()


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "reference", "status", "amount", "currency", "channel", "paid_at", "created_at"]
        read_only_fields = fields
