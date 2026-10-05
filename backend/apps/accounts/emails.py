from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_verification_token


def _send(subject, template_name, context, to_email):
    html_body = render_to_string(f"emails/{template_name}.html", context)
    send_mail(
        subject=subject,
        message=html_body,
        html_message=html_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


def send_verification_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    link = f"{settings.FRONTEND_URL}/verify-email/{uid}/{token}"
    _send(
        subject="Confirm your email — GO herbal",
        template_name="verify_email",
        context={"user": user, "link": link},
        to_email=user.email,
    )


def send_password_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"
    _send(
        subject="Reset your password — GO herbal",
        template_name="password_reset",
        context={"user": user, "link": link},
        to_email=user.email,
    )


def send_welcome_email(user):
    _send(
        subject="Welcome to GO herbal",
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
