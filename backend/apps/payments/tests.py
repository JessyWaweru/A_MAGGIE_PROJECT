import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orders.models import Order, OrderItem
from apps.products.models import Product

from .models import Payment

SECRET = "sk_test_secret"


def paystack_post(client, event: dict, secret=SECRET):
    body = json.dumps(event).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    return client.generic(
        "POST", "/api/payments/webhook/paystack/", body, content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=signature,
    )


@override_settings(PAYSTACK_SECRET_KEY=SECRET)
class PaymentSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="x", is_email_verified=True)
        self.product = Product.objects.create(name="Moringa Powder", price=500, stock_quantity=10)
        self.order = Order.objects.create(
            user=self.user, full_name="Buyer", phone_number="0712345678", delivery_method="pickup",
            subtotal=Decimal("1000.00"), shipping_fee=Decimal("0.00"), total_amount=Decimal("1000.00"),
        )
        OrderItem.objects.create(order=self.order, product=self.product, product_name="Moringa Powder", unit_price=500, quantity=2)
        self.payment = Payment.objects.create(order=self.order, amount=self.order.total_amount)
        self.client = APIClient()

    def charge(self, amount=100000, currency="KES"):
        return {"event": "charge.success", "data": {"reference": self.payment.reference, "amount": amount, "currency": currency, "channel": "card"}}

    def assert_paid(self, paid: bool):
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID if paid else Order.Status.PENDING)
        self.assertEqual(self.product.stock_quantity, 8 if paid else 10)

    def test_full_payment_marks_order_paid_once(self):
        self.assertEqual(paystack_post(self.client, self.charge()).status_code, 200)
        paystack_post(self.client, self.charge())  # Paystack retries; must not double-count stock
        self.assert_paid(True)

    def test_forged_webhook_is_rejected(self):
        res = paystack_post(self.client, self.charge(), secret="guessed-secret")
        self.assertEqual(res.status_code, 401)
        self.assert_paid(False)

    def test_unsigned_webhook_is_rejected(self):
        res = self.client.post("/api/payments/webhook/paystack/", self.charge(), format="json")
        self.assertEqual(res.status_code, 401)
        self.assert_paid(False)

    def test_underpayment_does_not_fulfil(self):
        paystack_post(self.client, self.charge(amount=100))  # KES 1 instead of KES 1,000
        self.assert_paid(False)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)

    def test_wrong_currency_does_not_fulfil(self):
        paystack_post(self.client, self.charge(currency="NGN"))
        self.assert_paid(False)

    @patch("apps.payments.views.verify_transaction")
    def test_verify_checks_amount_too(self, verify):
        verify.return_value = {"status": "success", "amount": 100, "currency": "KES"}
        self.client.force_authenticate(self.user)
        self.client.get(f"/api/payments/verify/{self.payment.reference}/")
        self.assert_paid(False)

    def test_cannot_pay_or_verify_someone_elses_order(self):
        other = User.objects.create_user(email="other@example.com", password="x", is_email_verified=True)
        self.client.force_authenticate(other)
        res = self.client.post("/api/payments/initialize/", {"order_number": self.order.order_number}, format="json")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.client.get(f"/api/payments/verify/{self.payment.reference}/").status_code, 404)

    @patch("apps.payments.views.initialize_transaction", return_value={"authorization_url": "https://paystack.test/x"})
    def test_charge_amount_comes_from_the_order_not_the_request(self, initialize):
        self.client.force_authenticate(self.user)
        self.client.post("/api/payments/initialize/", {"order_number": self.order.order_number, "amount": 1}, format="json")
        self.assertEqual(initialize.call_args.kwargs["amount"], Decimal("1000.00"))

    def test_paid_order_cannot_be_paid_again(self):
        paystack_post(self.client, self.charge())
        self.client.force_authenticate(self.user)
        res = self.client.post("/api/payments/initialize/", {"order_number": self.order.order_number}, format="json")
        self.assertEqual(res.status_code, 400)
