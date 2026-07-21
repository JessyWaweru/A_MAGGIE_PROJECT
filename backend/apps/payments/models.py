import uuid

from django.db import models

from apps.core.models import TimeStampedModel
from apps.orders.models import Order


def generate_reference():
    return f"HRPAY-{uuid.uuid4().hex[:16].upper()}"


class Payment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    provider = models.CharField(max_length=20, default="paystack")
    reference = models.CharField(max_length=64, unique=True, default=generate_reference)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    authorization_url = models.URLField(blank=True)
    channel = models.CharField(max_length=30, blank=True, help_text="e.g. card, mobile_money")
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} ({self.status})"
