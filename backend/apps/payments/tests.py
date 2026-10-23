import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
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

    def test_paid_order_is_emailed_once_after_saving(self):
        with self.captureOnCommitCallbacks(execute=True):
            paystack_post(self.client, self.charge())
            paystack_post(self.client, self.charge())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.order.order_number, mail.outbox[0].subject)

    def test_email_failure_does_not_undo_payment(self):
        with patch("apps.accounts.emails.send_mail", side_effect=OSError("mail server down")):
            with self.assertLogs("apps.accounts.emails", "ERROR"), self.captureOnCommitCallbacks(execute=True):
                res = paystack_post(self.client, self.charge())
        self.assertEqual(res.status_code, 200)
        self.assert_paid(True)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)

    def test_only_needed_payment_details_are_stored(self):
        event = self.charge()
        event["data"].update(ip_address="41.90.1.2", customer={"email": "buyer@example.com"}, authorization={"last4": "4081"})
        paystack_post(self.client, event)
        self.payment.refresh_from_db()
        self.assertEqual(set(self.payment.raw_response), {"reference", "amount", "currency", "channel"})

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


@override_settings(PAYSTACK_SECRET_KEY=SECRET)
class MpesaChargeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="x", is_email_verified=True)
        self.order = Order.objects.create(
            user=self.user, full_name="Buyer", phone_number="0712345678", delivery_method="pickup",
            subtotal=Decimal("1000.00"), shipping_fee=Decimal("0.00"), total_amount=Decimal("1000.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def charge(self, phone="0712 345 678"):
        return self.client.post(
            "/api/payments/mpesa/", {"order_number": self.order.order_number, "phone_number": phone}, format="json"
        )

    @patch("apps.payments.views.charge_mpesa", return_value={"status": "pay_offline", "display_text": "Enter your PIN"})
    def test_sends_prompt_for_the_order_total(self, charge_mpesa):
        res = self.charge()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "pending")
        self.assertEqual(res.data["display_text"], "Enter your PIN")
        kwargs = charge_mpesa.call_args.kwargs
        self.assertEqual(kwargs["phone"], "+254712345678")
        self.assertEqual(kwargs["amount"], Decimal("1000.00"))
        self.assertEqual(kwargs["reference"], res.data["reference"])

    @patch("apps.payments.views.charge_mpesa", return_value={"status": "pay_offline"})
    def test_phone_formats_are_normalised(self, charge_mpesa):
        for phone, expected in [("+254 712 345 678", "+254712345678"), ("254110000000", "+254110000000"), ("712345678", "+254712345678")]:
            Payment.objects.all().delete()  # clear the open prompt from the previous loop
            self.assertEqual(self.charge(phone).status_code, 201, phone)
            self.assertEqual(charge_mpesa.call_args.kwargs["phone"], expected)

    @patch("apps.payments.views.charge_mpesa")
    def test_rejects_non_kenyan_or_malformed_numbers(self, charge_mpesa):
        for phone in ["0812345678", "+255712345678", "07123", "hello"]:
            self.assertEqual(self.charge(phone).status_code, 400, phone)
        charge_mpesa.assert_not_called()

    @patch("apps.payments.views.charge_mpesa", return_value={"status": "pay_offline"})
    def test_phone_number_is_not_stored(self, _):
        self.charge()
        payment = Payment.objects.get()
        self.assertNotIn("712345678", json.dumps(payment.raw_response))
        self.assertEqual(payment.channel, "mobile_money")

    @patch("apps.payments.views.charge_mpesa", return_value={"status": "pay_offline"})
    def test_no_second_prompt_while_first_is_open(self, charge_mpesa):
        self.assertEqual(self.charge().status_code, 201)
        self.assertEqual(self.charge().status_code, 409)
        self.assertEqual(charge_mpesa.call_count, 1)

    @patch("apps.payments.views.charge_mpesa", return_value={"status": "failed", "message": "Insufficient funds"})
    def test_failed_prompt_can_be_retried(self, charge_mpesa):
        res = self.charge()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["detail"], "Insufficient funds")
        self.assertEqual(Payment.objects.get().status, Payment.Status.FAILED)
        charge_mpesa.return_value = {"status": "pay_offline"}
        self.assertEqual(self.charge().status_code, 201)

    @patch("apps.payments.views.verify_transaction", return_value={"status": "ongoing"})
    @patch("apps.payments.views.charge_mpesa", return_value={"status": "pay_offline"})
    def test_polling_while_waiting_for_pin_keeps_payment_pending(self, _, __):
        reference = self.charge().data["reference"]
        res = self.client.get(f"/api/payments/verify/{reference}/")
        self.assertEqual(res.data["status"], "pending")

    @patch("apps.payments.views.charge_mpesa", return_value={"status": "pay_offline"})
    def test_webhook_completes_the_order(self, _):
        reference = self.charge().data["reference"]
        paystack_post(APIClient(), {"event": "charge.success", "data": {"reference": reference, "amount": 100000, "currency": "KES", "channel": "mobile_money"}})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    @patch("apps.payments.views.charge_mpesa")
    def test_cannot_prompt_for_someone_elses_order(self, charge_mpesa):
        other = User.objects.create_user(email="other@example.com", password="x", is_email_verified=True)
        self.client.force_authenticate(other)
        self.assertEqual(self.charge().status_code, 404)
        charge_mpesa.assert_not_called()
