from decimal import Decimal

from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.products.models import Product

from .models import DeliveryOption, Order, OrderStatusEvent

# Points relative to the default dispatch point (Nairobi CBD, -1.2841, 36.8233)
CBD = {"latitude": "-1.285000", "longitude": "36.824000"}  # ~0.1 km
WESTLANDS = {"latitude": "-1.267500", "longitude": "36.807000"}  # ~2.6 km
RUIRU = {"latitude": "-1.146000", "longitude": "36.961000"}  # ~21.6 km
NAKURU = {"latitude": "-0.303100", "longitude": "36.080000"}  # ~136 km


class DeliveryCheckoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="wanjiru@example.com", password="x", first_name="Wanjiru")
        cls.product = Product.objects.create(name="Moringa Powder", price=500, stock_quantity=10)
        # The seed migration has already created the default options.
        cls.pickup = DeliveryOption.objects.get(method="pickup")
        cls.agent = DeliveryOption.objects.get(method="agent")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.post("/api/orders/cart/items/", {"product_id": str(self.product.id), "quantity": 2}, format="json")

    def checkout(self, **payload):
        return self.client.post("/api/orders/checkout/", {"full_name": "Wanjiru K", "phone_number": "0712345678", **payload}, format="json")

    def test_store_pickup_needs_no_address_and_charges_pickup_fee(self):
        res = self.checkout(delivery_method="pickup")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(Decimal(body["shipping_fee"]), self.pickup.fee)
        self.assertEqual(Decimal(body["total_amount"]), Decimal("1000") + self.pickup.fee)
        self.assertIn("Collect from", body["shipping_address_text"])

    def test_rider_fee_comes_from_the_pin_not_the_client(self):
        res = self.checkout(
            delivery_method="rider",
            delivery_option_id=str(self.pickup.id),  # ignored for riders
            address_line1="Woodvale Grove",
            city="Nairobi",
            landmark="Blue gate opposite Sarit",
            **RUIRU,
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["delivery_option_name"], "Rider — Greater Nairobi")
        self.assertEqual(Decimal(res.json()["shipping_fee"]), Decimal("400"))

    def test_phone_is_stored_dialable_and_junk_refused(self):
        self.assertEqual(self.checkout(delivery_method="pickup").json()["phone_number"], "+254712345678")
        self.client.post("/api/orders/cart/items/", {"product_id": str(self.product.id)}, format="json")
        self.assertEqual(self.checkout(delivery_method="pickup", phone_number="12").status_code, 400)

    def test_rider_zones_get_pricier_with_distance(self):
        quotes = [self.client.get("/api/orders/delivery-quote/", point).json() for point in (CBD, WESTLANDS, RUIRU)]
        fees = [Decimal(q["option"]["fee"]) for q in quotes]
        self.assertEqual(fees, [Decimal("150"), Decimal("150"), Decimal("400")])

    def test_rider_outside_coverage_is_refused(self):
        self.assertFalse(self.client.get("/api/orders/delivery-quote/", NAKURU).json()["available"])
        res = self.checkout(delivery_method="rider", address_line1="Kenyatta Ave", city="Nakuru", **NAKURU)
        self.assertEqual(res.status_code, 400)
        self.assertIn("outside our rider delivery area", str(res.json()))

    def test_rider_needs_a_pin(self):
        res = self.checkout(delivery_method="rider", address_line1="Ngong Road", city="Nairobi")
        self.assertEqual(res.status_code, 400)
        self.assertIn("pin", str(res.json()))

    def test_saved_address_pin_is_used(self):
        address = Address.objects.create(
            user=self.user, full_name="Wanjiru K", phone_number="0712345678", address_line1="Kitengela Rd", city="Kajiado",
            latitude=Decimal(RUIRU["latitude"]), longitude=Decimal(RUIRU["longitude"]),
        )
        res = self.client.post("/api/orders/checkout/", {"delivery_method": "rider", "address_id": str(address.id)}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(Decimal(res.json()["shipping_fee"]), Decimal("400"))

    def test_agent_delivery_requires_an_agent(self):
        self.assertEqual(self.checkout(delivery_method="agent").status_code, 400)
        res = self.checkout(delivery_method="agent", pickup_agent="Kisumu — Mega Plaza")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["pickup_agent"], "Kisumu — Mega Plaza")
        self.assertEqual(Decimal(res.json()["shipping_fee"]), self.agent.fee)

    def test_inactive_option_is_unavailable(self):
        DeliveryOption.objects.filter(method="agent").update(is_active=False)
        res = self.checkout(delivery_method="agent", pickup_agent="Kisumu")
        self.assertEqual(res.status_code, 400)


class OrderTimelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="otieno@example.com", password="x")
        self.order = Order.objects.create(user=self.user, full_name="Otieno", phone_number="0700", delivery_method="rider")

    def test_status_changes_are_recorded(self):
        self.order.status = Order.Status.PAID
        self.order.save()
        self.order.save()  # no change, no new event
        statuses = list(OrderStatusEvent.objects.filter(order=self.order).values_list("status", flat=True))
        self.assertEqual(statuses, ["pending", "paid"])

    def test_customer_is_emailed_when_order_goes_out(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.order.status = Order.Status.OUT_FOR_DELIVERY
            self.order.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("on its way", mail.outbox[0].subject)

    def test_failed_status_email_does_not_block_the_update(self):
        with self.settings(EMAIL_BACKEND="apps.core.email_backend.ResendEmailBackend", RESEND_API_KEY=""):
            with self.assertLogs("apps.orders.notifications", "ERROR"), self.captureOnCommitCallbacks(execute=True):
                self.order.status = Order.Status.DELIVERED
                self.order.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)


class RiderMessageTests(TestCase):
    def test_message_has_contact_address_directions_and_pin(self):
        from django.utils import timezone

        user = User.objects.create_user(email="njeri@example.com", password="x")
        order = Order.objects.create(
            user=user, full_name="Njeri W", phone_number="+254712345678", address_line1="Riverside Dr",
            address_line2="Kileleshwa", city="Nairobi", landmark="Blue gate", latitude=Decimal("-1.27"),
            longitude=Decimal("36.79"), delivery_method="rider", paid_at=timezone.now(),
        )
        message = order.rider_message
        for expected in ["Njeri W — +254712345678", "Riverside Dr, Kileleshwa, Nairobi", "Directions: Blue gate",
                         "maps/search/?api=1&query=-1.27", "nothing to collect"]:
            self.assertIn(expected, message)

    def test_only_for_rider_orders(self):
        user = User.objects.create_user(email="otieno2@example.com", password="x")
        self.assertEqual(Order.objects.create(user=user, delivery_method="pickup").rider_message, "")
