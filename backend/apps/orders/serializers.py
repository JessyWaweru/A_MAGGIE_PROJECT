from rest_framework import serializers

from apps.accounts.models import Address
from apps.products.models import Product
from apps.products.serializers import ProductListSerializer

from .models import Cart, CartItem, Order, OrderItem


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


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shipping_address_text = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "items",
            "full_name",
            "phone_number",
            "shipping_address_text",
            "subtotal",
            "shipping_fee",
            "total_amount",
            "currency",
            "customer_notes",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    address_id = serializers.PrimaryKeyRelatedField(queryset=Address.objects.none(), required=False)
    full_name = serializers.CharField(max_length=150, required=False)
    phone_number = serializers.CharField(max_length=20, required=False)
    address_line1 = serializers.CharField(max_length=255, required=False)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False)
    county_or_state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, default="Kenya")
    customer_notes = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["address_id"].queryset = Address.objects.filter(user=request.user)

    def validate(self, attrs):
        if "address_id" not in attrs:
            required_inline = ["full_name", "phone_number", "address_line1", "city"]
            missing = [f for f in required_inline if not attrs.get(f)]
            if missing:
                raise serializers.ValidationError(
                    f"Provide address_id or these fields: {', '.join(missing)}."
                )
        return attrs
