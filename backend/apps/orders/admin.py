from django.contrib import admin

from .models import Cart, CartItem, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "user", "status", "total_amount", "currency", "created_at"]
    list_filter = ["status", "country"]
    search_fields = ["order_number", "user__email", "full_name"]
    readonly_fields = ["order_number", "subtotal", "total_amount", "paid_at"]
    inlines = [OrderItemInline]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "total_items", "updated_at"]
    search_fields = ["user__email"]
    inlines = [CartItemInline]
