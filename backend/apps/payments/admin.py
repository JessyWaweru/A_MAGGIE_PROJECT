from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "order", "consultation", "status", "amount", "currency", "paid_at"]
    list_filter = ["status", "provider"]
    search_fields = ["reference", "order__order_number", "consultation__reference"]
    readonly_fields = ["reference", "raw_response"]
