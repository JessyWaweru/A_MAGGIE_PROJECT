from django.contrib import admin
from django.utils.html import format_html

from .models import Cart, CartItem, DeliveryOption, Order, OrderItem, OrderStatusEvent


@admin.register(DeliveryOption)
class DeliveryOptionAdmin(admin.ModelAdmin):
    list_display = ["name", "method", "fee", "max_distance_km", "eta", "is_active", "sort_order"]
    list_editable = ["fee", "is_active", "sort_order"]
    list_filter = ["method", "is_active"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity"]
    can_delete = False


class OrderStatusEventInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0
    readonly_fields = ["status", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "user", "status", "delivery_option_name", "total_amount", "created_at"]
    list_filter = ["status", "delivery_method", "county_or_state"]
    search_fields = ["order_number", "user__email", "full_name", "phone_number"]
    readonly_fields = [
        "order_number",
        "subtotal",
        "shipping_fee",
        "total_amount",
        "paid_at",
        "delivery_method",
        "delivery_option_name",
        "open_in_maps",
    ]
    fieldsets = [
        (None, {"fields": ["order_number", "user", "status", "paid_at", "customer_notes"]}),
        (
            "Delivery",
            {
                "fields": [
                    "delivery_method",
                    "delivery_option_name",
                    "full_name",
                    "phone_number",
                    "address_line1",
                    "address_line2",
                    "city",
                    "county_or_state",
                    "landmark",
                    "open_in_maps",
                    "pickup_agent",
                    "tracking_code",
                ]
            },
        ),
        ("Amounts", {"fields": ["subtotal", "shipping_fee", "total_amount", "currency"]}),
    ]
    inlines = [OrderItemInline, OrderStatusEventInline]

    @admin.display(description="Customer pin")
    def open_in_maps(self, obj):
        if not obj.map_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open in Google Maps ↗</a>', obj.map_url)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "total_items", "updated_at"]
    search_fields = ["user__email"]
    inlines = [CartItemInline]
