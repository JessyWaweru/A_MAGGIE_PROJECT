import math
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.products.models import Product


def generate_order_number():
    return f"HR-{uuid.uuid4().hex[:10].upper()}"


class Cart(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")

    def __str__(self):
        return f"Cart for {self.user.email}"

    @property
    def subtotal(self):
        return sum((item.line_total for item in self.items.select_related("product")), Decimal("0.00"))

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["cart", "product"], name="one_line_per_product_per_cart")]

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def line_total(self):
        return self.product.price * self.quantity


def distance_km(lat1, lng1, lat2, lng2) -> float:
    """Straight-line (great-circle) distance between two points."""
    lat1, lng1, lat2, lng2 = map(math.radians, (float(lat1), float(lng1), float(lat2), float(lng2)))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


class DeliveryOption(TimeStampedModel):
    """A way to get an order to the customer, with its fee. Managed from the admin."""

    class Method(models.TextChoices):
        PICKUP = "pickup", "Store pickup"
        RIDER = "rider", "Rider delivery"
        AGENT = "agent", "Pickup agent (e.g. Pickup Mtaani)"

    method = models.CharField(max_length=10, choices=Method.choices)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    eta = models.CharField(max_length=60, blank=True, help_text="Shown to customers, e.g. 'Same day'")
    fee = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    max_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Rider zones only: furthest straight-line distance from the dispatch point this fee covers.",
    )
    address = models.CharField(max_length=255, blank=True, help_text="Store pickup only: where to collect.")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "fee"]

    def __str__(self):
        return f"{self.name} ({self.fee})"

    def clean(self):
        if self.method == self.Method.RIDER and self.max_distance_km is None:
            raise ValidationError({"max_distance_km": "Rider zones need a maximum distance."})


class Rider(TimeStampedModel):
    """A delivery rider. Riders have no account: each delivery reaches them as an SMS link."""

    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, help_text="Delivery links are texted here.")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, help_text="e.g. motorbike plate, usual area")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.phone_number})"

    def clean(self):
        from apps.accounts.validators import normalize_phone

        self.phone_number = normalize_phone(self.phone_number)


def rider_zone_for(latitude, longitude):
    """The cheapest active rider zone that reaches this point, and the distance to it."""
    km = distance_km(settings.DISPATCH_LATITUDE, settings.DISPATCH_LONGITUDE, latitude, longitude)
    zone = (
        DeliveryOption.objects.filter(method=DeliveryOption.Method.RIDER, is_active=True, max_distance_km__gte=km)
        .order_by("max_distance_km")
        .first()
    )
    return zone, km


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Being prepared"
        READY_FOR_PICKUP = "ready_for_pickup", "Ready for pickup"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        SHIPPED = "shipped", "Sent to pickup agent"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, default=generate_order_number, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    delivery_option = models.ForeignKey(
        DeliveryOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    # Snapshots, so changing an option later doesn't rewrite past orders
    delivery_method = models.CharField(max_length=10, choices=DeliveryOption.Method.choices, blank=True)
    delivery_option_name = models.CharField(max_length=100, blank=True)
    # Rider deliveries: the customer's map pin and directions for the rider
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    landmark = models.CharField(max_length=255, blank=True)
    # Agent deliveries: the agent point the customer will collect from
    pickup_agent = models.CharField(max_length=255, blank=True)
    tracking_code = models.CharField(
        max_length=100, blank=True, help_text="Courier/agent parcel code, shown to the customer."
    )
    rider = models.ForeignKey(
        Rider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Choosing a rider texts them a private link to this delivery.",
    )
    # The secret in the rider's link. Replaced when the rider changes, cleared once the delivery ends.
    rider_token = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    rider_assigned_at = models.DateTimeField(null=True, blank=True, editable=False)

    # Shipping address snapshot (kept even if the user later edits/deletes the saved Address)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    county_or_state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default="Kenya")

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="KES")

    customer_notes = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    # Once an order reaches one of these, its rider link stops working.
    RIDER_LINK_CLOSED = {"delivered", "cancelled", "refunded"}
    # A rider can only be sent out once the order is paid and not yet delivered.
    DISPATCHABLE = {"paid", "processing", "out_for_delivery"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_status = self.status
        self._saved_rider_id = self.rider_id

    def __str__(self):
        return self.order_number

    def clean(self):
        if self.rider_id and self.rider_id != self._saved_rider_id:
            if self.delivery_method != DeliveryOption.Method.RIDER:
                raise ValidationError({"rider": "Only rider-delivery orders can be given a rider."})
            if self.status not in self.DISPATCHABLE:
                raise ValidationError({"rider": "Assign a rider once the order is paid and before it's delivered."})

    @property
    def rider_changed(self):
        return self.rider_id != self._saved_rider_id

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        token_fields = set()
        if self.rider_changed:
            self.rider_token = secrets.token_urlsafe(24) if self.rider_id else ""
            self.rider_assigned_at = timezone.now() if self.rider_id else None
            token_fields = {"rider_token", "rider_assigned_at"}
        if self.status in self.RIDER_LINK_CLOSED and self.rider_token:
            self.rider_token = ""
            token_fields.add("rider_token")
        if kwargs.get("update_fields") is not None and token_fields:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | token_fields
        super().save(*args, **kwargs)
        self._saved_rider_id = self.rider_id
        if is_new or self.status != self._saved_status:
            OrderStatusEvent.objects.create(order=self, status=self.status)
            if not is_new:
                from .notifications import notify_status_change

                notify_status_change(self)
            self._saved_status = self.status

    @property
    def rider_message(self):
        """Everything a rider needs, ready to paste into WhatsApp or SMS."""
        if self.delivery_method != DeliveryOption.Method.RIDER:
            return ""
        lines = [
            f"GOherbal delivery #{self.order_number}",
            f"Customer: {self.full_name} — {self.phone_number}",
            "Address: " + ", ".join(p for p in [self.address_line1, self.address_line2, self.city] if p),
        ]
        if self.landmark:
            lines.append(f"Directions: {self.landmark}")
        if self.map_url:
            lines.append(f"Pin: {self.map_url}")
        lines.append("Already paid, nothing to collect." if self.paid_at else "NOT PAID YET, don't deliver.")
        lines.append("Please call the customer before you arrive.")
        return "\n".join(lines)

    @property
    def map_url(self):
        if self.latitude is None or self.longitude is None:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={self.latitude},{self.longitude}"

    @property
    def shipping_address_text(self):
        if self.delivery_method == DeliveryOption.Method.PICKUP:
            return f"Collect from {self.delivery_option.address}" if self.delivery_option else "Store pickup"
        if self.delivery_method == DeliveryOption.Method.AGENT:
            return f"Collect from agent: {self.pickup_agent}"
        parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.county_or_state,
            self.postal_code,
            self.country,
        ]
        text = ", ".join(p for p in parts if p)
        return f"{text} (near {self.landmark})" if self.landmark else text


class OrderItem(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name="order_items")

    # Snapshots so historical orders stay accurate if the product changes later
    product_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class OrderStatusEvent(models.Model):
    """One entry in an order's timeline, recorded whenever its status changes."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_events")
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.order} → {self.status}"
