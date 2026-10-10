from django.contrib import admin, messages
from django.utils.html import format_html

from apps.core.sms import SMSError

from .dispatch import text_rider
from .models import Cart, CartItem, DeliveryOption, Order, OrderItem, OrderStatusEvent, Rider


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ["name", "phone_number", "is_active", "notes"]
    list_editable = ["is_active"]
    search_fields = ["name", "phone_number"]


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
    list_display = ["order_number", "user", "status", "delivery_option_name", "rider", "total_amount", "created_at"]
    list_filter = ["status", "delivery_method", "rider", "county_or_state"]
    actions = ["resend_rider_link"]
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
        "message_for_rider",
        "rider_link_status",
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
                    "rider",
                    "rider_link_status",
                    "message_for_rider",
                    "pickup_agent",
                    "tracking_code",
                ]
            },
        ),
        ("Amounts", {"fields": ["subtotal", "shipping_fee", "total_amount", "currency"]}),
    ]
    inlines = [OrderItemInline, OrderStatusEventInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "rider":
            kwargs["queryset"] = Rider.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        newly_assigned = obj.rider_changed and obj.rider_id
        super().save_model(request, obj, form, change)
        if newly_assigned:
            self._text_rider(request, obj)

    def _text_rider(self, request, order):
        try:
            text_rider(order)
        except SMSError as exc:
            self.message_user(
                request,
                f"{order.order_number}: couldn't text {order.rider.name} ({exc}). "
                "Fix the SMS settings or the rider's number, then use “Resend delivery link”.",
                messages.ERROR,
            )
        else:
            self.message_user(request, f"{order.order_number}: delivery link texted to {order.rider.name}.", messages.SUCCESS)

    @admin.action(description="Resend delivery link to the assigned rider")
    def resend_rider_link(self, request, queryset):
        for order in queryset.select_related("rider"):
            if order.rider_id and order.rider_token:
                self._text_rider(request, order)
            else:
                self.message_user(request, f"{order.order_number}: no active rider link.", messages.WARNING)

    @admin.display(description="Rider link")
    def rider_link_status(self, obj):
        if obj.rider_token:
            return f"Active, texted {obj.rider_assigned_at:%d %b %H:%M}" if obj.rider_assigned_at else "Active"
        if obj.rider_id:
            return "Closed (delivery finished)"
        return "—"

    @admin.display(description="Customer pin")
    def open_in_maps(self, obj):
        if not obj.map_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open in Google Maps ↗</a>', obj.map_url)

    @admin.display(description="Message for the rider")
    def message_for_rider(self, obj):
        if not obj.rider_message:
            return "—"
        return format_html(
            '<textarea readonly rows="8" cols="60" onclick="this.select()" style="font-family: monospace;">{}</textarea>'
            "<br><small>Click to select, then copy and send to the rider.</small>",
            obj.rider_message,
        )


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "total_items", "updated_at"]
    search_fields = ["user__email"]
    inlines = [CartItemInline]

