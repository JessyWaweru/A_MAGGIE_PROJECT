from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.payments.handlers import fulfill_successful_payment
from apps.payments.models import Payment

from .models import Consultation, Expert


def make_expert(**overrides):
    fields = {
        "slug": "achieng-herbalist",
        "name": "Achieng Odhiambo",
        "kind": Expert.Kind.HERBAL_COACH,
        "title": "Clinical Herbalist",
        "bio": "Ten years of practice.",
        "fee": 1500,
        "email": "achieng@example.com",
        **overrides,
    }
    return Expert.objects.create(**fields)


@override_settings(CONSULTATIONS_TEAM_EMAIL="team@example.com")
class BookingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="kamau@example.com", password="x", first_name="Kamau")
        self.expert = make_expert()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def book(self, **overrides):
        payload = {
            "expert_id": str(self.expert.id),
            "mode": "whatsapp",
            "preferred_time": (timezone.now() + timedelta(days=1)).isoformat(),
            "phone_number": "0712345678",
            "concern": "Trouble sleeping for three weeks.",
            "consent": True,
            **overrides,
        }
        return self.client.post("/api/consultations/bookings/", payload, format="json")

    def test_booking_starts_unpaid_at_the_experts_fee(self):
        res = self.book()
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["status"], "pending_payment")
        self.assertEqual(res.json()["fee"], "1500.00")
        self.assertEqual(len(mail.outbox), 0)

    def test_consent_is_required(self):
        self.assertEqual(self.book(consent=False).status_code, 400)

    def test_mode_must_be_offered(self):
        self.assertEqual(self.book(mode="video").status_code, 400)

    def test_time_must_be_in_the_future(self):
        self.assertEqual(self.book(preferred_time=timezone.now().isoformat()).status_code, 400)

    def test_payment_confirms_booking_and_emails_everyone(self):
        consultation = Consultation.objects.get(reference=self.book().json()["reference"])
        payment = Payment.objects.create(consultation=consultation, amount=consultation.fee)
        fulfill_successful_payment(payment, {"channel": "mobile_money"})
        fulfill_successful_payment(payment, {"channel": "mobile_money"})  # webhook + verify both fire

        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CONFIRMED)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["achieng@example.com", "kamau@example.com", "team@example.com"])

    def test_free_session_is_confirmed_without_payment(self):
        self.expert.fee = 0
        self.expert.save()
        res = self.book()
        self.assertEqual(res.json()["status"], "confirmed")
        self.assertEqual(len(mail.outbox), 3)

    def test_users_only_see_their_own_bookings(self):
        reference = self.book().json()["reference"]
        other = APIClient()
        other.force_authenticate(User.objects.create_user(email="other@example.com", password="x"))
        self.assertEqual(other.get(f"/api/consultations/bookings/{reference}/").status_code, 404)

    @patch("apps.payments.views.initialize_transaction", return_value={"authorization_url": "https://paystack.test/x"})
    def test_payment_can_be_started_for_a_booking(self, _):
        reference = self.book().json()["reference"]
        res = self.client.post("/api/payments/initialize/", {"consultation_reference": reference}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(Payment.objects.get().amount, 1500)


class ExpertTests(TestCase):
    def test_medical_specialists_need_a_licence(self):
        expert = Expert(slug="dr", name="Dr Mwangi", kind=Expert.Kind.MEDICAL_SPECIALIST, title="GP", bio=".", fee=2000)
        with self.assertRaises(ValidationError):
            expert.full_clean()

    def test_public_listing_hides_private_email(self):
        make_expert()
        body = APIClient().get("/api/consultations/experts/").json()
        self.assertEqual(len(body), 1)
        self.assertNotIn("email", body[0])
        self.assertEqual(body[0]["modes"], ["whatsapp", "phone"])
