from rest_framework import serializers

from apps.accounts.models import Address
from apps.accounts.serializers import validate_phone
from apps.products.models import Product
from apps.products.serializers import ProductListSerializer

from .models import Cart, CartItem, DeliveryOption, Order, OrderItem, OrderStatusEvent, rider_zone_for


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity", "line_total", "created_at"]
        read_only_fields = ["id", "created_at"]


class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(status="active"))
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_items = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "items", "subtotal", "total_items", "updated_at"]


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    product_slug = serializers.SlugField(source="product.slug", read_only=True, allow_null=True)
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product_slug", "product_image", "product_name", "unit_price", "quantity", "line_total"]

    def get_product_image(self, obj):
        return obj.product.primary_image_url if obj.product else None


class DeliveryOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryOption
        fields = ["id", "method", "name", "description", "eta", "fee", "max_distance_km", "address", "latitude", "longitude"]


class DeliveryQuoteSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)


class RiderDeliverySerializer(serializers.ModelSerializer):
    """What the rider's link shows: only what's needed to deliver this one order."""

    items = serializers.SerializerMethodField()
    rider_name = serializers.CharField(source="rider.name", read_only=True)
    is_paid = serializers.SerializerMethodField()
    directions_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "order_number",
            "status",
            "rider_name",
            "full_name",
            "phone_number",
            "address_line1",
            "address_line2",
            "city",
            "landmark",
            "latitude",
            "longitude",
            "directions_url",
            "items",
            "is_paid",
        ]

    def get_items(self, obj):
        return [{"name": item.product_name, "quantity": item.quantity} for item in obj.items.all()]

    def get_is_paid(self, obj):
        return obj.paid_at is not None

    def get_directions_url(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return ""
        return f"https://www.google.com/maps/dir/?api=1&destination={obj.latitude},{obj.longitude}"


class OrderStatusEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusEvent
        fields = ["status", "created_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_events = OrderStatusEventSerializer(many=True, read_only=True)
    shipping_address_text = serializers.ReadOnlyField()
    rider = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "status_events",
            "items",
            "full_name",
            "phone_number",
            "shipping_address_text",
            "delivery_method",
            "delivery_option_name",
            "latitude",
            "longitude",
            "landmark",
            "pickup_agent",
            "tracking_code",
            "rider",
            "subtotal",
            "shipping_fee",
            "total_amount",
            "currency",
            "customer_notes",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_rider(self, obj):
        # The customer sees who's coming only while the order is on its way.
        if obj.rider_id and obj.status == Order.Status.OUT_FOR_DELIVERY:
            return {"name": obj.rider.name, "phone_number": obj.rider.phone_number}
        return None


ADDRESS_FIELDS = [
    "full_name",
    "phone_number",
    "address_line1",
    "address_line2",
    "city",
    "county_or_state",
    "postal_code",
    "country",
    "landmark",
    "latitude",
    "longitude",
]


class CheckoutSerializer(serializers.Serializer):
    """Validates checkout input and resolves the delivery option, fee and address snapshot.

    For rider delivery the zone (and so the fee) comes from the map pin, never from the client.
    """

    delivery_method = serializers.ChoiceField(choices=DeliveryOption.Method.choices)
    delivery_option_id = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryOption.objects.filter(is_active=True), required=False
    )
    address_id = serializers.PrimaryKeyRelatedField(queryset=Address.objects.none(), required=False)
    full_name = serializers.CharField(max_length=150, required=False)
    phone_number = serializers.CharField(max_length=20, required=False)
    address_line1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    county_or_state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, default="Kenya")
    landmark = serializers.CharField(max_length=255, required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    pickup_agent = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_notes = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["address_id"].queryset = Address.objects.filter(user=request.user)

    def validate(self, attrs):
        method = attrs["delivery_method"]
        if "address_id" in attrs:
            address = attrs["address_id"]
            fields = {name: getattr(address, name) for name in ADDRESS_FIELDS}
        else:
            fields = {name: attrs.get(name) for name in ADDRESS_FIELDS}
        fields = {k: ("" if v is None and k not in ("latitude", "longitude") else v) for k, v in fields.items()}
        fields["country"] = fields["country"] or "Kenya"

        required = ["full_name", "phone_number"]
        if method == DeliveryOption.Method.RIDER:
            required += ["address_line1", "city"]
        missing = [f for f in required if not fields.get(f)]
        if missing:
            raise serializers.ValidationError(f"Please provide: {', '.join(f.replace('_', ' ') for f in missing)}.")
        # Saved addresses from before phone validation may hold free text; checkout always stores a dialable number.
        fields["phone_number"] = validate_phone(fields["phone_number"])

        if method == DeliveryOption.Method.RIDER:
            if fields["latitude"] is None or fields["longitude"] is None:
                raise serializers.ValidationError("Drop a pin on the map so our rider can find you.")
            option, _ = rider_zone_for(fields["latitude"], fields["longitude"])
            if option is None:
                raise serializers.ValidationError(
                    "That location is outside our rider delivery area. Choose a pickup agent near you instead."
                )
        else:
            option = attrs.get("delivery_option_id") or DeliveryOption.objects.filter(
                method=method, is_active=True
            ).first()
            if option is None or option.method != method:
                raise serializers.ValidationError("That delivery option isn't available right now.")
            if method == DeliveryOption.Method.AGENT and not attrs.get("pickup_agent", "").strip():
                raise serializers.ValidationError("Tell us which pickup agent you'd like to collect from.")
            # Pickup and agent orders don't need a street address or pin.
            fields.update(latitude=None, longitude=None)

        attrs["delivery_option"] = option
        attrs["address_fields"] = fields
        return attrs
