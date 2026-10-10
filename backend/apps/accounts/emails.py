from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def _send(subject, template_name, context, to_email):
    html_body = render_to_string(f"emails/{template_name}.html", {"logo_url": settings.EMAIL_LOGO_URL, **context})
    send_mail(
        subject=subject,
        message=html_body,
        html_message=html_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


def send_verification_code_email(user, code, minutes_valid):
    _send(
        subject=f"{code} is your GOherbal verification code",
        template_name="verify_email",
        context={"user": user, "code": code, "minutes_valid": minutes_valid},
        to_email=user.email,
    )


def send_password_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"
    _send(
        subject="Reset your password — GOherbal",
        template_name="password_reset",
        context={"user": user, "link": link},
        to_email=user.email,
    )


def send_welcome_email(user):
    _send(
        subject="Welcome to GOherbal",
        template_name="welcome",
        context={"user": user, "FRONTEND_URL": settings.FRONTEND_URL},
        to_email=user.email,
    )


def send_order_confirmation_email(order):
    _send(
        subject=f"Order confirmed — #{order.order_number}",
        template_name="order_confirmation",
        context={"order": order},
        to_email=order.user.email,
    )


ORDER_STATUS_COPY = {
    "ready_for_pickup": ("Your order is ready for pickup", "Your order is packed and waiting for you at our store."),
    "out_for_delivery": ("Your order is on its way", "A rider has your order and is heading to you. They'll call before arriving."),
    "shipped": (
        "Your order is at the pickup agent",
        "Your order has been sent to your chosen pickup agent. You'll receive an SMS when it's ready to collect.",
    ),
    "delivered": ("Your order has been delivered", "Your order has been delivered. We hope you enjoy your remedies!"),
}


def send_order_status_email(order):
    headline, message = ORDER_STATUS_COPY[order.status]
    _send(
        subject=f"{headline} — #{order.order_number}",
        template_name="order_status",
        context={"order": order, "headline": headline, "message": message, "FRONTEND_URL": settings.FRONTEND_URL},
        to_email=order.user.email,
    )


def send_consultation_confirmed_emails(consultation):
    _send(
        subject=f"Your consultation with {consultation.expert.name} is booked",
        template_name="consultation_confirmed",
        context={"consultation": consultation, "FRONTEND_URL": settings.FRONTEND_URL},
        to_email=consultation.user.email,
    )
    for team_email in {consultation.expert.email, settings.CONSULTATIONS_TEAM_EMAIL} - {""}:
        _send(
            subject=f"New paid consultation {consultation.reference} — please schedule",
            template_name="consultation_new_booking",
            context={"consultation": consultation},
            to_email=team_email,
        )


def send_email_change_code(user, new_email, code):
    _send(
        subject=f"{code} is your code to confirm your new GOherbal email",
        template_name="email_change_code",
        context={"user": user, "code": code, "new_email": new_email},
        to_email=new_email,
    )


def send_email_changed_alert(user, old_email, revert_token):
    _send(
        subject="Your GOherbal email address was changed",
        template_name="email_changed_alert",
        context={
            "user": user,
            "new_email": user.email,
            "revert_link": f"{settings.FRONTEND_URL}/revert-email?token={quote(revert_token)}",
        },
        to_email=old_email,
    )


def send_password_changed_alert(user):
    _send(
        subject="Your GOherbal password was changed",
        template_name="password_changed_alert",
        context={"user": user, "reset_link": f"{settings.FRONTEND_URL}/forgot-password"},
        to_email=user.email,
    )
