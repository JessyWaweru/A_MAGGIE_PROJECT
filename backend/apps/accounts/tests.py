import re
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .cookies import ACCESS_COOKIE, REFRESH_COOKIE
from .models import EmailVerificationCode, User

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
        payload = {"email": "Ama@Example.com", "password": STRONG, "first_name": "Ama", **overrides}
        return self.client.post("/api/auth/register/", payload, format="json")

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
