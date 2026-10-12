import logging

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .forwarding import fetch_received_email, forward_inbound_email
from .models import InboundEmail, NewsletterSubscriber
from .newsletter import unsubscribe
from .serializers import ContactMessageSerializer, NewsletterSubscriberSerializer
from .webhooks import WebhookVerificationError, verify_svix_signature

logger = logging.getLogger(__name__)


class NewsletterSubscribeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = NewsletterSubscriberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        if NewsletterSubscriber.objects.filter(email__iexact=email, is_active=True).exists():
            return Response({"detail": "You're already on the garden letter. Thanks!"}, status=status.HTTP_200_OK)
        serializer.save()
        return Response({"detail": "Subscribed! Welcome to the herb garden."}, status=status.HTTP_201_CREATED)


class NewsletterUnsubscribeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not unsubscribe(request.data.get("token", "")):
            return Response({"detail": "This unsubscribe link is invalid."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "You've been unsubscribed from the garden letter."})


class ContactMessageView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Message received. We'll get back to you soon."}, status=status.HTTP_201_CREATED)


class InboundEmailWebhookView(APIView):
    """Receives Resend's `email.received` webhook for @goherbal.health addresses.

    Field names for the inbound payload aren't nailed down in Resend's public docs
    at the time this was written, so every plausible spelling is tried and the
    complete raw payload is always kept, so nothing is lost if a guess is wrong.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = settings.RESEND_INBOUND_WEBHOOK_SECRET
        if not secret:
            logger.error("RESEND_INBOUND_WEBHOOK_SECRET is not configured; rejecting inbound webhook.")
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            verify_svix_signature(secret, request.body, request.headers)
        except WebhookVerificationError:
            logger.warning("Rejected inbound email webhook with an invalid signature.")
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data
        event_type = payload.get("type", "")
        if event_type and event_type not in ("email.received", "inbox.email.received"):
            # Any other event type Resend might route to the same URL - accept but ignore.
            return Response(status=status.HTTP_200_OK)

        data = payload.get("data", payload) or {}

        def first_present(*keys, default=""):
            for key in keys:
                value = data.get(key)
                if value:
                    return value
            return default

        to_field = first_present("to", "to_address", "recipient", default="")
        to_address = to_field[0] if isinstance(to_field, list) else to_field

        email_id = data.get("email_id") or data.get("id") or ""
        text_body = first_present("text", "text_body", "plain")
        html_body = first_present("html", "html_body")
        subject = first_present("subject")
        if not (text_body or html_body):
            # Resend's webhook only carries metadata; the body has to be fetched separately.
            fetched = fetch_received_email(email_id)
            text_body = fetched.get("text") or ""
            html_body = fetched.get("html") or ""
            subject = subject or fetched.get("subject") or ""

        inbound = InboundEmail.objects.create(
            message_id=first_present("message_id", "id", "email_id"),
            from_address=first_present("from", "from_address", "sender"),
            to_address=to_address,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            raw_payload=payload,
        )
        try:
            forward_inbound_email(inbound)
        except Exception:
            # Still acknowledge: the email is saved, and a retry from Resend would store it twice.
            logger.exception("Could not forward inbound email %s", inbound.pk)
        return Response(status=status.HTTP_200_OK)
