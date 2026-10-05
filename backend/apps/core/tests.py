import base64
import hashlib
import hmac
import json
import time

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import InboundEmail
from .webhooks import WebhookVerificationError, verify_svix_signature

SECRET = "whsec_" + base64.b64encode(b"a-test-signing-secret-32-bytes!!").decode()


def sign(secret, msg_id, timestamp, body: bytes):
    secret_bytes = base64.b64decode(secret.removeprefix("whsec_"))
    signed_content = f"{msg_id}.{timestamp}.".encode() + body
    sig = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()
    return f"v1,{sig}"


class VerifySvixSignatureTests(TestCase):
    def test_valid_signature_passes(self):
        body = b'{"hello":"world"}'
        ts = str(int(time.time()))
        headers = {"svix-id": "msg_1", "svix-timestamp": ts, "svix-signature": sign(SECRET, "msg_1", ts, body)}
        verify_svix_signature(SECRET, body, headers)  # does not raise

    def test_tampered_body_rejected(self):
        body = b'{"hello":"world"}'
        ts = str(int(time.time()))
        headers = {"svix-id": "msg_1", "svix-timestamp": ts, "svix-signature": sign(SECRET, "msg_1", ts, body)}
        with self.assertRaises(WebhookVerificationError):
            verify_svix_signature(SECRET, b'{"hello":"tampered"}', headers)

    def test_old_timestamp_rejected(self):
        body = b"{}"
        ts = str(int(time.time()) - 3600)
        headers = {"svix-id": "msg_1", "svix-timestamp": ts, "svix-signature": sign(SECRET, "msg_1", ts, body)}
        with self.assertRaises(WebhookVerificationError):
            verify_svix_signature(SECRET, body, headers)

    def test_missing_headers_rejected(self):
        with self.assertRaises(WebhookVerificationError):
            verify_svix_signature(SECRET, b"{}", {})


@override_settings(RESEND_INBOUND_WEBHOOK_SECRET=SECRET)
class InboundEmailWebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/webhooks/inbound-email/"

    def post_signed(self, data: dict, msg_id="msg_1", ts=None):
        body = json.dumps(data).encode()
        ts = ts or str(int(time.time()))
        headers = {
            "HTTP_SVIX_ID": msg_id,
            "HTTP_SVIX_TIMESTAMP": ts,
            "HTTP_SVIX_SIGNATURE": sign(SECRET, msg_id, ts, body),
        }
        return self.client.generic("POST", self.url, data=body, content_type="application/json", **headers)

    def test_valid_event_is_stored(self):
        payload = {
            "type": "email.received",
            "data": {
                "message_id": "m1",
                "from": "customer@example.com",
                "to": ["hello@goherbal.health"],
                "subject": "Question about an order",
                "text": "Hi there",
                "html": "<p>Hi there</p>",
            },
        }
        res = self.post_signed(payload)
        self.assertEqual(res.status_code, 200)
        email = InboundEmail.objects.get()
        self.assertEqual(email.from_address, "customer@example.com")
        self.assertEqual(email.to_address, "hello@goherbal.health")
        self.assertEqual(email.subject, "Question about an order")
        self.assertEqual(email.raw_payload, payload)

    def test_unsigned_request_rejected(self):
        res = self.client.post(self.url, {"type": "email.received", "data": {}}, format="json")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(InboundEmail.objects.count(), 0)

    def test_tampered_signature_rejected(self):
        body = json.dumps({"type": "email.received", "data": {"subject": "x"}}).encode()
        ts = str(int(time.time()))
        res = self.client.generic(
            "POST",
            self.url,
            data=body,
            content_type="application/json",
            HTTP_SVIX_ID="msg_1",
            HTTP_SVIX_TIMESTAMP=ts,
            HTTP_SVIX_SIGNATURE="v1,not-a-real-signature",
        )
        self.assertEqual(res.status_code, 401)

    def test_other_event_types_acknowledged_but_ignored(self):
        res = self.post_signed({"type": "email.delivered", "data": {}})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(InboundEmail.objects.count(), 0)

    @override_settings(RESEND_INBOUND_WEBHOOK_SECRET="")
    def test_missing_secret_returns_503(self):
        res = self.post_signed({"type": "email.received", "data": {}})
        self.assertEqual(res.status_code, 503)
