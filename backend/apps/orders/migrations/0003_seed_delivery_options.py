from decimal import Decimal

from django.db import migrations

# Placeholder fees and pickup address; the business edits these in the admin.
DEFAULT_OPTIONS = [
    {
        "method": "pickup",
        "name": "Store pickup — Nairobi CBD",
        "description": "Collect from our CBD shop. We'll email you when it's ready.",
        "eta": "Ready in 1–3 hours",
        "fee": Decimal("50"),
        "address": "GOherbal Shop, Kenyatta Avenue, Nairobi CBD (placeholder)",
        "latitude": Decimal("-1.284100"),
        "longitude": Decimal("36.823300"),
        "sort_order": 0,
    },
    {
        "method": "rider",
        "name": "Rider — Nairobi CBD",
        "description": "Within about 3 km of the CBD.",
        "eta": "Same day",
        "fee": Decimal("150"),
        "max_distance_km": Decimal("3"),
        "sort_order": 10,
    },
    {
        "method": "rider",
        "name": "Rider — Inner Nairobi",
        "description": "Westlands, Kilimani, South B/C, Eastleigh and similar.",
        "eta": "Same day",
        "fee": Decimal("250"),
        "max_distance_km": Decimal("10"),
        "sort_order": 11,
    },
    {
        "method": "rider",
        "name": "Rider — Greater Nairobi",
        "description": "Ruiru, Kitengela, Ngong, Syokimau, Kikuyu and similar.",
        "eta": "Same or next day",
        "fee": Decimal("400"),
        "max_distance_km": Decimal("25"),
        "sort_order": 12,
    },
    {
        "method": "agent",
        "name": "Pickup Mtaani agent",
        "description": "Collect from a Pickup Mtaani agent near you, anywhere in Kenya.",
        "eta": "1–3 days",
        "fee": Decimal("200"),
        "sort_order": 20,
    },
]


def seed(apps, schema_editor):
    DeliveryOption = apps.get_model("orders", "DeliveryOption")
    if not DeliveryOption.objects.exists():
        DeliveryOption.objects.bulk_create(DeliveryOption(**option) for option in DEFAULT_OPTIONS)

    # Give existing orders a timeline entry for their current status.
    Order = apps.get_model("orders", "Order")
    OrderStatusEvent = apps.get_model("orders", "OrderStatusEvent")
    for order in Order.objects.filter(status_events__isnull=True):
        event = OrderStatusEvent.objects.create(order=order, status=order.status)
        OrderStatusEvent.objects.filter(pk=event.pk).update(created_at=order.updated_at)


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_deliveryoption_order_delivery_method_and_more")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
