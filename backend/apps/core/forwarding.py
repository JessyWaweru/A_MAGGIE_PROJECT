import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def _domain(address: str) -> str:
    return address.rpartition("@")[2].strip(">").lower()


def forward_inbound_email(inbound):
    """Forward a received @goherbal.health email to the team's real inbox.

    Replies go to the original sender. The copy stored in the admin is kept either way.
    """
    forward_to = settings.INBOUND_FORWARD_TO
    if not forward_to:
        return
    if inbound.to_address and _domain(forward_to) == _domain(inbound.to_address):
        # Forwarding to the same domain would come straight back through this webhook, forever.
        logger.error("INBOUND_FORWARD_TO must be outside the receiving domain; not forwarding.")
        return

    text = inbound.text_body or (
        "This email's content wasn't included in the notification. Read it in the admin under Core → Inbound emails."
    )
    header = f"From: {inbound.from_address or 'unknown sender'}\nTo: {inbound.to_address}\n\n"
    message = EmailMultiAlternatives(
        subject=inbound.subject or "(no subject)",
        body=header + text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[forward_to],
        reply_to=[inbound.from_address] if inbound.from_address else None,
    )
    if inbound.html_body:
        message.attach_alternative(inbound.html_body, "text/html")
    message.send()
