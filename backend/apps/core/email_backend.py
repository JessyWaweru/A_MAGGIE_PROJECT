"""Django email backend that sends through Resend's HTTPS API.

Render's free tier blocks outbound SMTP ports, so the SMTP relay can't be used there.
"""

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not settings.RESEND_API_KEY:
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured("RESEND_API_KEY is not set, so no email can be sent.")

        sent = 0
        for message in email_messages:
            try:
                self._send(message)
            except requests.RequestException:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def _send(self, message):
        payload = {
            "from": message.from_email,
            "to": message.to,
            "subject": message.subject,
            "text": message.body,
        }
        if message.cc:
            payload["cc"] = message.cc
        if message.bcc:
            payload["bcc"] = message.bcc
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                payload["html"] = content

        response = requests.post(
            RESEND_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            timeout=settings.EMAIL_TIMEOUT,
        )
        if response.status_code >= 400:
            # Resend explains rejections (unverified domain, bad key) in the body.
            raise requests.HTTPError(f"Resend rejected the email ({response.status_code}): {response.text}", response=response)
