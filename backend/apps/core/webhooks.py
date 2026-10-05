"""Verification for Resend's inbound webhooks (Svix-signed).

Resend signs webhooks the way Svix does: the signed content is
"{svix-id}.{svix-timestamp}.{raw body}", HMAC-SHA256'd with the base64 part of
the signing secret (after its "whsec_" prefix), base64-encoded, and compared
against one of the space-separated "v1,<sig>" values in svix-signature.

No Svix/Resend SDK is required for this - it's plain hmac/hashlib, so it has
no new dependency and nothing to keep in sync with an SDK version.
"""

import base64
import hashlib
import hmac
import time


class WebhookVerificationError(Exception):
    pass


def verify_svix_signature(secret: str, raw_body: bytes, headers) -> None:
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")
    if not (svix_id and svix_timestamp and svix_signature):
        raise WebhookVerificationError("Missing svix-* headers.")

    try:
        if abs(time.time() - int(svix_timestamp)) > 60 * 5:
            raise WebhookVerificationError("Webhook timestamp is too old.")
    except ValueError:
        raise WebhookVerificationError("Invalid svix-timestamp header.")

    secret_bytes = base64.b64decode(secret.removeprefix("whsec_"))
    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + raw_body
    expected = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()

    given_signatures = [part.split(",", 1)[1] for part in svix_signature.split() if "," in part]
    if not any(hmac.compare_digest(expected, given) for given in given_signatures):
        raise WebhookVerificationError("Signature mismatch.")
