"""Account deletion: erase the person, keep the sales records.

Orders and payments are business records that must be kept for accounting and tax,
so instead of deleting the user row (which would cascade to them), the account is
anonymised: personal details are wiped everywhere and sign-in becomes impossible.
"""

import uuid

from django.db import transaction

from apps.consultations.models import Consultation
from apps.core.models import NewsletterSubscriber
from apps.orders.models import Order

from .emails import send_account_deleted_email
from .models import EmailChangeRequest, EmailVerificationCode
from .security import end_all_sessions, send_after_commit

ACTIVE_ORDER_STATUSES = [
    Order.Status.PAID,
    Order.Status.PROCESSING,
    Order.Status.READY_FOR_PICKUP,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.SHIPPED,
]
UPCOMING_CONSULTATION_STATUSES = [Consultation.Status.CONFIRMED, Consultation.Status.SCHEDULED]


def blockers(user) -> list[str]:
    """Reasons the account can't be deleted yet: things the customer has paid for that aren't finished."""
    reasons = []
    orders = Order.objects.filter(user=user, status__in=ACTIVE_ORDER_STATUSES).count()
    if orders:
        reasons.append(f"{orders} order{'s' if orders != 1 else ''} still on {'their' if orders != 1 else 'its'} way")
    sessions = Consultation.objects.filter(user=user, status__in=UPCOMING_CONSULTATION_STATUSES).count()
    if sessions:
        reasons.append(f"{sessions} upcoming consultation{'s' if sessions != 1 else ''}")
    return reasons


@transaction.atomic
def delete_account(user):
    email, first_name = user.email, user.first_name

    # Unpaid orders and bookings can simply be cancelled.
    Order.objects.filter(user=user, status=Order.Status.PENDING).update(status=Order.Status.CANCELLED)
    Consultation.objects.filter(user=user, status=Consultation.Status.PENDING_PAYMENT).update(
        status=Consultation.Status.CANCELLED
    )

    # Keep each order's items and amounts (and the town, for sales reports); drop who and where.
    Order.objects.filter(user=user).update(
        full_name="Deleted customer",
        phone_number="",
        address_line1="",
        address_line2="",
        postal_code="",
        landmark="",
        latitude=None,
        longitude=None,
        pickup_agent="",
        customer_notes="",
    )
    # Health details are sensitive personal data and go entirely.
    Consultation.objects.filter(user=user).update(concern="[deleted]", phone_number="", meeting_link="")

    user.addresses.all().delete()
    user.reviews.all().delete()
    user.wishlist_items.all().delete()
    if hasattr(user, "cart"):
        user.cart.delete()
    EmailVerificationCode.objects.filter(user=user).delete()
    EmailChangeRequest.objects.filter(user=user).delete()
    NewsletterSubscriber.objects.filter(email__iexact=email).delete()

    placeholder = f"deleted-{uuid.uuid4().hex}@deleted.invalid"
    user.email = placeholder
    user.username = placeholder
    user.first_name = ""
    user.last_name = ""
    user.phone_number = ""
    user.newsletter_opt_in = False
    user.is_email_verified = False
    user.is_active = False
    user.set_unusable_password()
    user.save()
    end_all_sessions(user)

    send_after_commit(send_account_deleted_email, email, first_name)
