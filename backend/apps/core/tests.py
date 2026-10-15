import base64
import hashlib
import hmac
import json
import time
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient

from .models import InboundEmail
from .throttling import client_ip
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

    @override_settings(RESEND_API_KEY="re_test")
    def test_body_is_fetched_when_webhook_has_none(self):
        payload = {"type": "email.received", "data": {"email_id": "e1", "from": "a@example.com", "to": ["hello@goherbal.health"]}}
        fetched = mock.Mock()
        fetched.json.return_value = {"text": "The message", "html": "<p>The message</p>", "subject": "Hello"}
        with mock.patch("apps.core.forwarding.requests.get", return_value=fetched) as get:
            res = self.post_signed(payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("emails/receiving/e1", get.call_args.args[0])
        email = InboundEmail.objects.get()
        self.assertEqual(email.text_body, "The message")
        self.assertEqual(email.subject, "Hello")

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


BOOKING_ALERT = {
    "type": "email.received",
    "data": {
        "message_id": "m2",
        "from": "customer@example.com",
        "to": ["consultations@goherbal.health"],
        "subject": "New paid consultation",
        "text": "Please schedule",
        "html": "<p>Please schedule</p>",
    },
}


@override_settings(RESEND_INBOUND_WEBHOOK_SECRET=SECRET, INBOUND_FORWARD_TO="team@example.com")
class InboundForwardingTests(TestCase):
    setUp = InboundEmailWebhookTests.setUp
    post_signed = InboundEmailWebhookTests.post_signed

    def test_received_email_is_forwarded_with_reply_to_sender(self):
        self.assertEqual(self.post_signed(BOOKING_ALERT).status_code, 200)
        self.assertEqual(InboundEmail.objects.count(), 1)
        forwarded = mail.outbox[0]
        self.assertEqual(forwarded.to, ["team@example.com"])
        self.assertEqual(forwarded.reply_to, ["customer@example.com"])
        self.assertEqual(forwarded.subject, "New paid consultation")
        self.assertIn("Please schedule", forwarded.body)

    @override_settings(INBOUND_FORWARD_TO="inbox@goherbal.health")
    def test_never_forwards_to_its_own_domain(self):
        self.post_signed(BOOKING_ALERT)
        self.assertEqual(len(mail.outbox), 0)

    def test_forwarding_failure_still_acknowledges_and_keeps_email(self):
        with override_settings(EMAIL_BACKEND="apps.core.email_backend.ResendEmailBackend", RESEND_API_KEY=""):
            res = self.post_signed(BOOKING_ALERT)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(InboundEmail.objects.count(), 1)


class NewsletterWelcomeTests(TestCase):
    def test_new_subscriber_gets_welcome_email_once(self):
        client = APIClient()
        with self.captureOnCommitCallbacks(execute=True):
            res = client.post("/api/newsletter/subscribe/", {"email": "reader@example.com"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reader@example.com"])
        self.assertIn("garden letter", mail.outbox[0].subject)

    def test_repeat_signup_is_friendly_and_sends_nothing(self):
        client = APIClient()
        with self.captureOnCommitCallbacks(execute=True):
            client.post("/api/newsletter/subscribe/", {"email": "reader@example.com"}, format="json")
            res = client.post("/api/newsletter/subscribe/", {"email": "reader@example.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("already", res.data["detail"])
        self.assertEqual(len(mail.outbox), 1)

    def test_unsubscribe_link_in_welcome_email_works(self):
        from urllib.parse import parse_qs, urlparse
        import re

        from .models import NewsletterSubscriber

        client = APIClient()
        with self.captureOnCommitCallbacks(execute=True):
            client.post("/api/newsletter/subscribe/", {"email": "reader@example.com"}, format="json")
        link = re.search(r'href="([^"]*unsubscribe[^"]*)"', mail.outbox[0].body).group(1)
        token = parse_qs(urlparse(link.replace("&amp;", "&")).query)["token"][0]
        res = client.post("/api/newsletter/unsubscribe/", {"token": token}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(NewsletterSubscriber.objects.get().is_active)

    def test_bad_unsubscribe_token_rejected(self):
        res = APIClient().post("/api/newsletter/unsubscribe/", {"token": "nope"}, format="json")
        self.assertEqual(res.status_code, 400)


@override_settings(INBOUND_FORWARD_TO="team@example.com")
class ContactForwardingTests(TestCase):
    def test_contact_message_is_forwarded_with_reply_to_sender(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = APIClient().post(
                "/api/contact/",
                {"name": "Ann", "email": "ann@example.com", "subject": "Order", "message": "Where is it?"},
                format="json",
            )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["team@example.com"])
        self.assertEqual(sent.reply_to, ["ann@example.com"])
        self.assertIn("Where is it?", sent.body)


class ClientIPTests(TestCase):
    def ip(self, **meta):
        request = RequestFactory().get("/", **meta)
        return client_ip(request)

    def test_direct_connection_uses_remote_addr(self):
        self.assertEqual(self.ip(REMOTE_ADDR="41.90.64.7"), "41.90.64.7")

    def test_client_written_forwarded_for_entries_are_ignored(self):
        # Render appends the real peer; whatever the client sent sits to its left.
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR="1.2.3.4, 41.90.64.7", REMOTE_ADDR="10.0.0.2"), "41.90.64.7")

    def test_internal_hops_are_skipped(self):
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR="1.2.3.4, 41.90.64.7, 10.1.2.3"), "41.90.64.7")

    def test_cloudflare_peer_trusts_cf_connecting_ip(self):
        ip = self.ip(HTTP_X_FORWARDED_FOR="1.2.3.4, 162.158.1.1", HTTP_CF_CONNECTING_IP="105.160.2.9")
        self.assertEqual(ip, "105.160.2.9")

    def test_cf_connecting_ip_from_anyone_else_is_ignored(self):
        ip = self.ip(HTTP_X_FORWARDED_FOR="41.90.64.7", HTTP_CF_CONNECTING_IP="105.160.2.9")
        self.assertEqual(ip, "41.90.64.7")


@override_settings(INBOUND_FORWARD_TO="")
class PublicFormThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_changing_forwarded_for_does_not_escape_the_limit(self):
        client = APIClient()
        statuses = [
            client.post(
                "/api/contact/",
                {"name": "Ama", "email": "ama@example.com", "message": "Hello there"},
                format="json",
                HTTP_X_FORWARDED_FOR=f"10.9.8.{n}, 41.90.64.7",
            ).status_code
            for n in range(6)
        ]
        self.assertEqual(statuses, [201] * 5 + [429])

    def test_overlong_contact_message_is_rejected(self):
        res = APIClient().post(
            "/api/contact/", {"name": "Ama", "email": "ama@example.com", "message": "x" * 5001}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("message", res.json())


class ApiDocsTests(TestCase):
    def test_api_docs_are_not_served_without_debug(self):
        self.assertEqual(APIClient().get("/api/docs/").status_code, 404)
        self.assertEqual(APIClient().get("/api/schema/").status_code, 404)
