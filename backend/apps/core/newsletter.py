from django.contrib.auth import get_user_model
from django.core import signing

from .models import NewsletterSubscriber

_SALT = "newsletter-unsubscribe"


def make_unsubscribe_token(email: str) -> str:
    # No expiry: an unsubscribe link in an old email must keep working.
    return signing.dumps(email.lower(), salt=_SALT)


def unsubscribe(token: str) -> bool:
    """Take the token's address off the garden letter. Returns False if the token is invalid."""
    try:
        email = signing.loads(token, salt=_SALT)
    except signing.BadSignature:
        return False
    NewsletterSubscriber.objects.filter(email__iexact=email).update(is_active=False)
    get_user_model().objects.filter(email__iexact=email).update(newsletter_opt_in=False)
    return True
