from urllib.parse import quote

from django.contrib import admin, messages
from django.utils.html import format_html

from apps.core.sms import SMSError

from .dispatch import rider_link, text_rider, texts_automatically
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
        if newly_assigned and texts_automatically():
            self._text_rider(request, obj)
        elif newly_assigned:
            self.message_user(
                request,
                f"{obj.order_number}: assigned to {obj.rider.name}. Send them the “Message for the rider” "
                "from this order (WhatsApp or SMS buttons below it).",
                messages.INFO,
            )

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
        if not texts_automatically():
            self.message_user(
                request,
                "Automatic SMS is off. Open the order and send the “Message for the rider” yourself.",
                messages.WARNING,
            )
            return
        for order in queryset.select_related("rider"):
            if order.rider_id and order.rider_token:
                self._text_rider(request, order)
            else:
                self.message_user(request, f"{order.order_number}: no active rider link.", messages.WARNING)

    @admin.display(description="Rider link")
    def rider_link_status(self, obj):
        if obj.rider_token:
            link = rider_link(obj)
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">{}</a><br><small>Assigned {}. Included in the message below.</small>',
                link,
                link,
                f"{obj.rider_assigned_at:%d %b %H:%M}" if obj.rider_assigned_at else "",
            )
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
        text = obj.rider_message
        phone = obj.rider.phone_number.lstrip("+") if obj.rider else ""
        whatsapp = f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}"
        sms = f"sms:{'+' + phone if phone else ''}?body={quote(text)}"
        hint = "" if obj.rider else " Choose a rider above and save first, so the message includes their link."
        return format_html(
            '<textarea id="rider-message" readonly rows="10" cols="64" onclick="this.select()" '
            'style="font-family: monospace;">{}</textarea><br>'
            '<button type="button" class="button" onclick="navigator.clipboard.writeText('
            "document.getElementById('rider-message').value).then(() => this.textContent = 'Copied ✓')\">Copy</button> "
            '<a class="button" href="{}" target="_blank" rel="noopener">Open in WhatsApp</a> '
            '<a class="button" href="{}">Open in SMS app</a>'
            "<br><small>{}{}</small>",
            text,
            whatsapp,
            sms,
            f"Sends to {obj.rider.name}." if obj.rider else "",
            hint,
        )


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "total_items", "updated_at"]
    search_fields = ["user__email"]
    inlines = [CartItemInline]

