import re
from urllib.parse import unquote
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .cookies import ACCESS_COOKIE, REFRESH_COOKIE
from .models import Address, EmailVerificationCode, User

STRONG = "Fern&Moss42"
FAST_HASHER = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


def last_code():
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].subject).group(1)


@FAST_HASHER
class SignUpFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        patcher = patch("apps.accounts.views.passes_turnstile", return_value=True)
        self.turnstile = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = APIClient()

    def register(self, **overrides):
        payload = {"email": "Ama@Example.com", "password": STRONG, "first_name": "Ama", "phone_number": "0712 345 678", **overrides}
        return self.client.post("/api/auth/register/", payload, format="json")

    def test_phone_is_required_and_normalized(self):
        self.assertIn("phone_number", self.register(phone_number="").json())
        self.assertIn("phone_number", self.register(phone_number="12345").json())
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(User.objects.get().phone_number, "+254712345678")

    def test_register_sends_code_and_issues_no_session(self):
        res = self.register()
        self.assertEqual(res.status_code, 201)
        self.assertNotIn("access", res.json())
        self.assertEqual(res.json()["email"], "ama@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(last_code(), EmailVerificationCode.objects.get().code_hash)

    def test_correct_code_signs_in_and_verifies(self):
        self.register()
        res = self.client.post("/api/auth/verify-email/", {"email": "ama@example.com", "code": last_code()}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("access", res.json())
        self.assertTrue(res.cookies[ACCESS_COOKIE]["httponly"])
        self.assertTrue(res.cookies[REFRESH_COOKIE]["httponly"])
        self.assertEqual(res.cookies[REFRESH_COOKIE]["path"], "/api/auth/")
        self.assertEqual(res.json()["user"]["first_name"], "Ama")
        self.assertTrue(User.objects.get().is_email_verified)

    def test_code_locks_after_five_wrong_guesses(self):
        self.register()
        code = last_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.client.post("/api/auth/verify-email/", {"email": "ama@example.com", "code": wrong}, format="json")
        res = self.client.post("/api/auth/verify-email/", {"email": "ama@example.com", "code": code}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "too_many_attempts")

    def test_expired_code_rejected(self):
        self.register()
        code = last_code()
        EmailVerificationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        res = self.client.post("/api/auth/verify-email/", {"email": "ama@example.com", "code": code}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_resend_respects_cooldown(self):
        self.register()
        self.client.post("/api/auth/verify-email/resend/", {"email": "ama@example.com"}, format="json")
        self.assertEqual(len(mail.outbox), 1)
        EmailVerificationCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        self.client.post("/api/auth/verify-email/resend/", {"email": "ama@example.com"}, format="json")
        self.assertEqual(len(mail.outbox), 2)

    def test_weak_password_rejected_with_reason(self):
        res = self.register(password="fernmoss42")
        self.assertEqual(res.status_code, 400)
        self.assertIn("uppercase", " ".join(res.json()["password"]))

    def test_first_name_required(self):
        self.assertEqual(self.register(first_name="  ").status_code, 400)

    def test_abandoned_signup_can_be_completed_again(self):
        self.register()
        EmailVerificationCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        res = self.register(first_name="Amani", password="Newer&Moss77")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().first_name, "Amani")

    def test_verified_email_cannot_register_again(self):
        User.objects.create_user("ama@example.com", STRONG, is_email_verified=True)
        self.assertEqual(self.register().status_code, 400)


@FAST_HASHER
class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user("kofi@example.com", STRONG, first_name="Kofi", is_email_verified=True)

    def login(self, password=STRONG, email="Kofi@Example.com"):
        return self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json")

    def test_success_sets_cookies_not_body_tokens(self):
        res = self.login()
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("access", res.json())
        self.assertNotIn("refresh", res.json())
        self.assertIn(ACCESS_COOKIE, res.cookies)

    def test_unknown_email_and_wrong_password_look_identical(self):
        a, b = self.login(email="nobody@example.com"), self.login(password="Wrong&Pass1")
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))
        self.assertEqual(a.status_code, 401)

    def test_lockout_after_five_failures_blocks_correct_password(self):
        for _ in range(5):
            self.login(password="Wrong&Pass1")
        res = self.login()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["code"], "account_locked")

    def test_lockout_expires(self):
        for _ in range(5):
            self.login(password="Wrong&Pass1")
        User.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.login().status_code, 200)

    def test_unverified_user_gets_code_instead_of_session(self):
        User.objects.update(is_email_verified=False)
        res = self.login()
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "email_not_verified")
        self.assertNotIn(ACCESS_COOKIE, res.cookies)
        self.assertEqual(len(mail.outbox), 1)


@FAST_HASHER
class BotCheckTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    @patch("apps.accounts.views.passes_turnstile", return_value=False)
    def test_failed_bot_check_blocks_signup_and_sends_nothing(self, _):
        res = self.client.post(
            "/api/auth/register/", {"email": "bot@example.com", "password": STRONG, "first_name": "Bot"}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "bot_check_failed")
        self.assertFalse(User.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    @patch("apps.accounts.views.passes_turnstile", return_value=False)
    def test_failed_bot_check_blocks_password_reset_email(self, _):
        User.objects.create_user("kofi@example.com", STRONG)
        res = self.client.post("/api/auth/password-reset/", {"email": "kofi@example.com"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(TURNSTILE_SECRET_KEY="")
    def test_turnstile_fails_closed_without_secret(self):
        from .turnstile import passes_turnstile

        self.assertFalse(passes_turnstile(MagicMock(META={}), "some-token"))

    @override_settings(TURNSTILE_SECRET_KEY="secret")
    def test_turnstile_asks_cloudflare(self):
        from .turnstile import passes_turnstile

        request = MagicMock(META={"HTTP_X_FORWARDED_FOR": "203.0.113.9, 10.0.0.1"})
        with patch("apps.accounts.turnstile.requests.post") as post:
            post.return_value.json.return_value = {"success": True}
            self.assertTrue(passes_turnstile(request, "tok"))
            self.assertEqual(post.call_args.kwargs["data"], {"secret": "secret", "response": "tok", "remoteip": "203.0.113.9"})
            post.return_value.json.return_value = {"success": False, "error-codes": ["invalid-input-response"]}
            self.assertFalse(passes_turnstile(request, "tok"))


@FAST_HASHER
class CookieSessionTests(TestCase):
    """Uses a client that enforces CSRF, like a real browser would."""

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        User.objects.create_user("kofi@example.com", STRONG, first_name="Kofi", is_email_verified=True)

    def csrf(self):
        return self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def login(self):
        token = self.csrf()
        return self.client.post(
            "/api/auth/login/", {"email": "kofi@example.com", "password": STRONG}, format="json", HTTP_X_CSRFTOKEN=token
        )

    def test_login_without_csrf_token_is_rejected(self):
        self.csrf()
        res = self.client.post("/api/auth/login/", {"email": "kofi@example.com", "password": STRONG}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_cookie_session_reads_profile(self):
        self.login()
        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["first_name"], "Kofi")

    def test_cookie_authenticated_write_requires_csrf(self):
        self.login()
        token = self.csrf()
        self.assertEqual(self.client.patch("/api/auth/me/", {"first_name": "K"}, format="json").status_code, 403)
        res = self.client.patch("/api/auth/me/", {"first_name": "K"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, 200)

    def test_refresh_rotates_and_old_refresh_token_dies(self):
        self.login()
        old_refresh = self.client.cookies[REFRESH_COOKIE].value
        token = self.csrf()
        res = self.client.post("/api/auth/login/refresh/", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.cookies[REFRESH_COOKIE].value, old_refresh)
        self.client.cookies[REFRESH_COOKIE] = old_refresh
        self.assertEqual(self.client.post("/api/auth/login/refresh/", HTTP_X_CSRFTOKEN=token).status_code, 401)

    def test_logout_clears_cookies_and_kills_refresh_token(self):
        self.login()
        refresh = self.client.cookies[REFRESH_COOKIE].value
        token = self.csrf()
        res = self.client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, 204)
        self.assertEqual(res.cookies[ACCESS_COOKIE].value, "")
        self.client.cookies[REFRESH_COOKIE] = refresh
        self.assertEqual(self.client.post("/api/auth/login/refresh/", HTTP_X_CSRFTOKEN=token).status_code, 401)


NEW_STRONG = "Cedar&Rain77"


@FAST_HASHER
class AccountSecurityTests(TestCase):
    """Two browsers signed in to one account: 'phone' makes the changes, 'laptop' plays the other device."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("kofi@example.com", STRONG, first_name="Kofi", is_email_verified=True)
        self.phone, self.laptop = APIClient(enforce_csrf_checks=True), APIClient(enforce_csrf_checks=True)
        for client in (self.phone, self.laptop):
            self.sign_in(client)

    def post(self, client, url, data=None):
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        return client.post(url, data or {}, format="json", HTTP_X_CSRFTOKEN=token)

    def sign_in(self, client, email="kofi@example.com", password=STRONG):
        return self.post(client, "/api/auth/login/", {"email": email, "password": password})

    def signed_in(self, client):
        return client.get("/api/auth/me/").status_code == 200

    def can_refresh(self, client):
        return self.post(client, "/api/auth/login/refresh/").status_code == 200

    # --- password change ---

    def test_password_change_signs_out_other_devices_only(self):
        res = self.post(self.phone, "/api/auth/change-password/", {"old_password": STRONG, "new_password": NEW_STRONG})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(self.signed_in(self.phone))
        self.assertFalse(self.signed_in(self.laptop))
        self.assertFalse(self.can_refresh(self.laptop))
        self.assertTrue(self.can_refresh(self.phone))

    def test_password_change_emails_an_alert(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post(self.phone, "/api/auth/change-password/", {"old_password": STRONG, "new_password": NEW_STRONG})
        self.assertIn("password was changed", mail.outbox[-1].subject)

    def test_wrong_current_password_is_400_not_401(self):
        res = self.post(self.phone, "/api/auth/change-password/", {"old_password": "Nope&Nope1", "new_password": NEW_STRONG})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "wrong_password")

    def test_guessing_the_password_from_a_stolen_session_locks_the_account(self):
        for _ in range(4):
            self.post(self.laptop, "/api/auth/change-password/", {"old_password": "Guess&Guess1", "new_password": NEW_STRONG})
        cache.clear()  # get past the per-minute throttle to reach the lockout
        res = self.post(self.laptop, "/api/auth/change-password/", {"old_password": "Guess&Guess2", "new_password": NEW_STRONG})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "account_locked")
        self.assertFalse(self.signed_in(self.phone))
        self.assertEqual(self.sign_in(APIClient(enforce_csrf_checks=True)).status_code, 429)

    def test_password_reset_signs_everyone_out(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        self.user.refresh_from_db()  # reset tokens depend on last_login, set by the sign-ins above
        payload = {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
            "new_password": NEW_STRONG,
        }
        self.assertEqual(self.post(APIClient(enforce_csrf_checks=True), "/api/auth/password-reset/confirm/", payload).status_code, 200)
        self.assertFalse(self.signed_in(self.phone))
        self.assertFalse(self.can_refresh(self.laptop))

    # --- email change ---

    def start_change(self, new_email="kofi.new@example.com", password=STRONG):
        return self.post(self.phone, "/api/auth/change-email/", {"new_email": new_email, "password": password})

    def emailed_code(self):
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].subject).group(1)

    def test_email_change_needs_code_from_new_address(self):
        self.assertEqual(self.start_change().status_code, 200)
        self.assertEqual(mail.outbox[-1].to, ["kofi.new@example.com"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "kofi@example.com")  # nothing changes until the code is confirmed

        self.assertEqual(self.post(self.phone, "/api/auth/change-email/confirm/", {"code": "000000"}).status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            res = self.post(self.phone, "/api/auth/change-email/confirm/", {"code": self.emailed_code()})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["user"]["email"], "kofi.new@example.com")

        alert = mail.outbox[-1]
        self.assertEqual(alert.to, ["kofi@example.com"])
        self.assertIn("/revert-email?token=", alert.body)
        self.assertTrue(self.signed_in(self.phone))
        self.assertFalse(self.signed_in(self.laptop))
        # Sign in now uses the new address only.
        fresh = APIClient(enforce_csrf_checks=True)
        self.assertEqual(self.sign_in(fresh).status_code, 401)
        self.assertEqual(self.sign_in(fresh, email="kofi.new@example.com").status_code, 200)

    def test_email_change_requires_current_password(self):
        res = self.start_change(password="Wrong&Pass1")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_take_an_address_already_in_use(self):
        User.objects.create_user("taken@example.com", STRONG)
        self.assertEqual(self.start_change(new_email="Taken@Example.com").status_code, 400)

    def test_address_claimed_while_code_pending_is_refused(self):
        self.start_change()
        code = self.emailed_code()
        User.objects.create_user("kofi.new@example.com", STRONG)
        self.assertEqual(self.post(self.phone, "/api/auth/change-email/confirm/", {"code": code}).status_code, 400)

    def test_code_dies_after_five_wrong_guesses(self):
        self.start_change()
        code = self.emailed_code()
        for _ in range(5):
            self.post(self.phone, "/api/auth/change-email/confirm/", {"code": "111111"})
        cache.clear()
        res = self.post(self.phone, "/api/auth/change-email/confirm/", {"code": code})
        self.assertEqual(res.json()["code"], "too_many_attempts")

    def test_undo_link_recovers_a_hijacked_account(self):
        # A hacker on the laptop changes the email...
        self.post(self.laptop, "/api/auth/change-email/", {"new_email": "hacker@evil.test", "password": STRONG})
        code = self.emailed_code()
        with self.captureOnCommitCallbacks(execute=True):
            self.post(self.laptop, "/api/auth/change-email/confirm/", {"code": code})
        link = mail.outbox[-1].body
        token = unquote(re.search(r"revert-email\?token=([^\"\s]+)", link).group(1))

        # ...the real owner clicks the link in the alert sent to their old address.
        with self.captureOnCommitCallbacks(execute=True):
            res = self.post(APIClient(enforce_csrf_checks=True), "/api/auth/change-email/revert/", {"token": token})
        self.assertEqual(res.status_code, 200, res.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "kofi@example.com")
        self.assertFalse(self.signed_in(self.laptop))
        self.assertIn("Reset your password", mail.outbox[-1].subject)
        self.assertEqual(mail.outbox[-1].to, ["kofi@example.com"])

    def test_tampered_undo_link_is_rejected(self):
        res = self.post(APIClient(enforce_csrf_checks=True), "/api/auth/change-email/revert/", {"token": "forged:token"})
        self.assertEqual(res.status_code, 400)

    def test_profile_cannot_change_email_directly(self):
        token = self.phone.get("/api/auth/csrf/").json()["csrfToken"]
        self.phone.patch("/api/auth/me/", {"email": "sneaky@example.com"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "kofi@example.com")


class PhoneNormalizationTests(TestCase):
    def test_kenyan_formats(self):
        from .validators import normalize_phone

        for raw in ["0712345678", "0712 345 678", "712345678", "254712345678", "+254 712-345-678", "(0712) 345678"]:
            self.assertEqual(normalize_phone(raw), "+254712345678", raw)
        self.assertEqual(normalize_phone("0110 123 456"), "+254110123456")
        self.assertEqual(normalize_phone("+44 7911 123456"), "+447911123456")

    def test_rejects_junk(self):
        from django.core.exceptions import ValidationError

        from .validators import normalize_phone

        for raw in ["", "12345", "0612345678", "07123456789", "phone"]:
            with self.assertRaises(ValidationError, msg=raw):
                normalize_phone(raw)


@FAST_HASHER
class ProfilePhoneTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user("wanjiru@example.com", STRONG))

    def test_profile_phone_is_normalized_and_cannot_be_cleared(self):
        self.assertEqual(self.client.patch("/api/auth/me/", {"phone_number": "0722 000 111"}, format="json").json()["phone_number"], "+254722000111")
        self.assertEqual(self.client.patch("/api/auth/me/", {"phone_number": ""}, format="json").status_code, 400)
        # Name-only edits still work for older accounts that never gave a number.
        self.assertEqual(self.client.patch("/api/auth/me/", {"first_name": "Wanjiru"}, format="json").status_code, 200)


@FAST_HASHER
class DeleteAccountTests(TestCase):
    def setUp(self):
        from apps.core.models import NewsletterSubscriber
        from apps.orders.models import Order
        from apps.products.models import Product, Review

        cache.clear()
        self.user = User.objects.create_user(
            "akinyi@example.com", STRONG, first_name="Akinyi", phone_number="+254712345678", is_email_verified=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        Address.objects.create(user=self.user, full_name="Akinyi", phone_number="0712", address_line1="Ngong Rd", city="Nairobi")
        product = Product.objects.create(name="Neem Balm", price=300)
        Review.objects.create(user=self.user, product=product, rating=5, title="Lovely", comment="Great")
        NewsletterSubscriber.objects.create(email="akinyi@example.com")
        self.delivered = Order.objects.create(
            user=self.user, full_name="Akinyi O", phone_number="+254712345678", address_line1="Ngong Rd", city="Nairobi",
            landmark="Blue gate", subtotal=300, total_amount=300, status=Order.Status.DELIVERED,
        )

    def delete(self, password=STRONG, confirm="DELETE"):
        return self.client.post("/api/auth/delete-account/", {"password": password, "confirm": confirm}, format="json")

    def test_deletes_the_person_but_keeps_the_sale(self):
        from apps.orders.models import Order

        with self.captureOnCommitCallbacks(execute=True):
            res = self.delete()
        self.assertEqual(res.status_code, 200, res.content)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())
        self.assertTrue(self.user.email.endswith("@deleted.invalid"))
        self.assertEqual((self.user.first_name, self.user.phone_number), ("", ""))
        self.assertFalse(self.user.addresses.exists())
        self.assertFalse(self.user.reviews.exists())

        order = Order.objects.get(pk=self.delivered.pk)
        self.assertEqual(order.total_amount, 300)  # the sale survives...
        self.assertEqual((order.full_name, order.phone_number, order.address_line1, order.landmark), ("Deleted customer", "", "", ""))

        self.assertEqual(mail.outbox[-1].to, ["akinyi@example.com"])
        self.assertIn("deleted", mail.outbox[-1].subject)

    def test_email_is_free_to_sign_up_again_and_old_login_fails(self):
        self.delete()
        anon = APIClient()
        self.assertEqual(anon.post("/api/auth/login/", {"email": "akinyi@example.com", "password": STRONG}, format="json").status_code, 401)
        self.assertFalse(User.objects.filter(email__iexact="akinyi@example.com").exists())

    def test_needs_password_and_typed_confirmation(self):
        self.assertEqual(self.delete(password="Wrong&Pass1").status_code, 400)
        self.assertEqual(self.delete(confirm="yes").status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_blocked_while_an_order_is_on_its_way(self):
        from apps.orders.models import Order

        Order.objects.create(user=self.user, full_name="A", phone_number="1", subtotal=1, total_amount=1, status=Order.Status.OUT_FOR_DELIVERY)
        self.assertEqual(self.client.get("/api/auth/delete-account/").json()["blockers"], ["1 order still on its way"])
        res = self.delete()
        self.assertEqual(res.status_code, 409)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_unpaid_orders_are_cancelled(self):
        from apps.orders.models import Order

        pending = Order.objects.create(user=self.user, full_name="A", phone_number="1", subtotal=1, total_amount=1)
        self.delete()
        pending.refresh_from_db()
        self.assertEqual(pending.status, Order.Status.CANCELLED)
